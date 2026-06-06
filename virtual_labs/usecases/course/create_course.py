"""Create a course.

Orchestrates:
1. Provision externals for a virtual lab (KC groups, accounting) via ledger
2. Provision externals for a project (KC groups, accounting) via same ledger
3. Single DB transaction: insert virtual lab + project + course
4. If anything fails, the ledger unwinds all external provisioning
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from uuid import UUID, uuid4

from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.ledger import Ledger, ledger_container
from virtual_labs.core.ledger.modules.virtual_lab import COURSE_LAB_POLICY
from virtual_labs.core.types import UserRoleEnum, VliAppResponse
from virtual_labs.domain.course import CourseCreateBody, CourseOut
from virtual_labs.infrastructure.db.models import (
    Course,
    CourseStatus,
    Project,
    VirtualLab,
)
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.infrastructure.kc.models import AuthUser, CreatedGroup
from virtual_labs.infrastructure.settings import settings
from virtual_labs.shared.group_namespace import (
    make_project_group_name,
    make_virtual_lab_group_name,
)
from virtual_labs.usecases import accounting as accounting_cases

GroupRole = dict[str, CreatedGroup]  # {"admin_group": ..., "member_group": ...}


# ──────────────────────────────────────────────────────────────────────
# Compensation helpers
# ──────────────────────────────────────────────────────────────────────


async def _make_kc_group_compensation(
    group: CreatedGroup,
) -> Callable[[], Awaitable[None]]:
    async def _undo() -> None:
        try:
            await KeycloakRealm.a_delete_group(group_id=group["id"])
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to delete KC group {group['id']}: {exc}")

    return _undo


# ──────────────────────────────────────────────────────────────────────
# Virtual Lab external provisioning
# ──────────────────────────────────────────────────────────────────────


async def _provision_vlab_keycloak(
    ledger: Ledger,
    lab_id: UUID4,
    owner_id: UUID4,
    lab_name: str,
) -> GroupRole:
    admin_group_name = make_virtual_lab_group_name(lab_id, UserRoleEnum.admin)
    member_group_name = make_virtual_lab_group_name(lab_id, UserRoleEnum.member)

    admin_group_id, member_group_id = await asyncio.gather(
        KeycloakRealm.a_create_group({"name": admin_group_name}),
        KeycloakRealm.a_create_group({"name": member_group_name}),
    )
    assert admin_group_id is not None
    assert member_group_id is not None

    admin_group: CreatedGroup = {"id": admin_group_id, "name": admin_group_name}
    member_group: CreatedGroup = {"id": member_group_id, "name": member_group_name}
    ledger.push(await _make_kc_group_compensation(admin_group))
    ledger.push(await _make_kc_group_compensation(member_group))

    # Add owner to admin group
    await KeycloakRealm.a_group_user_add(user_id=owner_id, group_id=admin_group["id"])

    return {"admin_group": admin_group, "member_group": member_group}


async def _provision_vlab_accounting(
    ledger: Ledger,
    lab_id: UUID4,
    lab_name: str,
) -> None:
    if settings.ACCOUNTING_BASE_URL is None:
        return
    await accounting_cases.create_virtual_lab_account(
        virtual_lab_id=lab_id,
        name=lab_name,
        balance=COURSE_LAB_POLICY.welcome_bonus,
    )

    async def _log_orphan() -> None:
        logger.warning(
            f"Orphan accounting account left for vlab {lab_id}; "
            "no delete endpoint available — reconcile manually."
        )

    ledger.push(_log_orphan)


# ──────────────────────────────────────────────────────────────────────
# Project external provisioning
# ──────────────────────────────────────────────────────────────────────


async def _provision_project_keycloak(
    ledger: Ledger,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    owner_id: UUID4,
    vlab_admin_group_id: str,
) -> tuple[CreatedGroup, CreatedGroup]:
    admin_group_name = make_project_group_name(
        virtual_lab_id, project_id, UserRoleEnum.admin
    )
    member_group_name = make_project_group_name(
        virtual_lab_id, project_id, UserRoleEnum.member
    )

    admin_group_id, member_group_id = await asyncio.gather(
        KeycloakRealm.a_create_group({"name": admin_group_name}),
        KeycloakRealm.a_create_group({"name": member_group_name}),
    )
    assert admin_group_id is not None
    assert member_group_id is not None

    admin_group: CreatedGroup = {"id": admin_group_id, "name": admin_group_name}
    member_group: CreatedGroup = {"id": member_group_id, "name": member_group_name}
    ledger.push(await _make_kc_group_compensation(admin_group))
    ledger.push(await _make_kc_group_compensation(member_group))

    # Add owner to project admin group
    await KeycloakRealm.a_group_user_add(user_id=owner_id, group_id=admin_group["id"])

    return admin_group, member_group


async def _provision_project_accounting(
    ledger: Ledger,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    project_name: str,
) -> None:
    if settings.ACCOUNTING_BASE_URL is None:
        return
    await accounting_cases.create_project_account(
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        name=project_name,
    )

    async def _log_orphan() -> None:
        logger.warning(
            f"Orphan accounting project for vlab={virtual_lab_id} "
            f"project={project_id}; reconcile manually."
        )

    ledger.push(_log_orphan)


# ──────────────────────────────────────────────────────────────────────
# Post-commit best-effort operations
# ──────────────────────────────────────────────────────────────────────

COURSE_PROJECT_INITIAL_CREDITS = 200.0


async def _seed_course_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
) -> None:
    """Credit the vlab, then transfer to the course project. Best-effort —
    failures are logged but do not roll back the course creation."""
    if settings.ACCOUNTING_BASE_URL is None:
        return
    try:
        # 1. Top up the vlab account
        await accounting_cases.top_up_virtual_lab_budget(
            virtual_lab_id=virtual_lab_id,
            amount=COURSE_PROJECT_INITIAL_CREDITS,
        )
        # 2. Transfer from vlab to project
        await accounting_cases.assign_project_budget(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            amount=COURSE_PROJECT_INITIAL_CREDITS,
        )
        logger.info(
            f"Assigned {COURSE_PROJECT_INITIAL_CREDITS} credits to "
            f"course project {project_id}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to seed budget for course project {project_id}: {exc}")


# ──────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────


async def create_course(
    db: AsyncSession,
    payload: CourseCreateBody,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseOut]:
    owner_id = UUID(auth[0].sub)
    owner_email = auth[0].email

    vlab_id: UUID4 = uuid4()
    project_id: UUID4 = uuid4()
    course_id: UUID4 = uuid4()

    project_name = f"{payload.name} - Template Project"

    async with ledger_container() as ledger:
        # ── Step 1: Provision vlab externals ──
        vlab_groups = await _provision_vlab_keycloak(
            ledger, vlab_id, owner_id, payload.name
        )
        await _provision_vlab_accounting(ledger, vlab_id, payload.name)

        # ── Step 2: Provision project externals ──
        proj_admin_group, proj_member_group = await _provision_project_keycloak(
            ledger,
            virtual_lab_id=vlab_id,
            project_id=project_id,
            owner_id=owner_id,
            vlab_admin_group_id=vlab_groups["admin_group"]["id"],
        )
        await _provision_project_accounting(ledger, vlab_id, project_id, project_name)

        # ── Step 3: Single DB transaction for all three records ──
        try:
            async with db.begin():
                # Insert virtual lab
                db_vlab = VirtualLab(
                    id=vlab_id,
                    owner_id=owner_id,
                    admin_group_id=vlab_groups["admin_group"]["id"],
                    member_group_id=vlab_groups["member_group"]["id"],
                    name=payload.name,
                    description=payload.description,
                    reference_email=payload.reference_email or owner_email,
                    entity=payload.entity,
                    compute_cell=payload.compute_cell,
                )
                db.add(db_vlab)
                await db.flush()

                # Insert project (template project for the course)
                db_project = Project(
                    id=project_id,
                    virtual_lab_id=vlab_id,
                    name=project_name,
                    description=f"Template project for course: {payload.name}",
                    admin_group_id=proj_admin_group["id"],
                    member_group_id=proj_member_group["id"],
                    owner_id=owner_id,
                )
                db.add(db_project)
                await db.flush()

                # Insert course
                db_course = Course(
                    id=course_id,
                    virtual_lab_id=vlab_id,
                    institution_id=payload.institution_id,
                    template_project_id=project_id,
                    start_date=payload.start_date,
                    end_date=payload.end_date,
                    last_drop_date=payload.last_drop_date,
                    status=CourseStatus.DRAFT,
                )
                db.add(db_course)
                await db.flush()
                await db.refresh(db_course)

        except IntegrityError as err:
            logger.error(f"DB integrity error during course creation: {err}")
            raise VliError(
                error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
                http_status_code=HTTPStatus.CONFLICT,
                message="Course creation failed due to a conflict",
            ) from err
        except SQLAlchemyError as err:
            logger.error(f"DB error during course creation: {err}")
            raise VliError(
                error_code=VliErrorCode.DATABASE_ERROR,
                http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                message="Course creation failed",
            ) from err

    # ── Post-commit: best-effort credit assignment ──
    await _seed_course_project_budget(vlab_id, project_id)

    return VliAppResponse[CourseOut](
        message="Course created successfully",
        data=CourseOut.model_validate(db_course),
    )
