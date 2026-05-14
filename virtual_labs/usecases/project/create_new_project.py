"""Create a new project inside an existing virtual lab.

1. Parallel preflight reads (vlab fetch + ownership/name checks).
2. External provisioning under a `SagaCompensator` — Keycloak
   admin/member groups + user attachments + (optionally) accounting
   project account. The pre-allocated `project_id` is the
   idempotency seed.
3. A single DB transaction (`async with session.begin():`) for the
   local project row, so a crash mid-write leaves no partial state
   while Keycloak leaks are torn down by the saga.
4. Post-commit best-effort work — first-project credit transfer —
   via `PostCommitActions`.

"""

from __future__ import annotations

import asyncio
from http import HTTPStatus as status
from typing import Awaitable, Callable
from uuid import UUID, uuid4

from keycloak import KeycloakError  # type: ignore[import-untyped]
from loguru import logger
from pydantic import UUID4
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.domain.project import (
    Project as ProjectSchema,
)
from virtual_labs.domain.project import (
    ProjectCreateExpand,
    ProjectCreateOut,
    ProjectCreationBody,
)
from virtual_labs.infrastructure.db.models import Project, VirtualLab
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.infrastructure.kc.models import (
    AuthUser,
    CreatedGroup,
    UserRepresentation,
)
from virtual_labs.infrastructure.settings import settings
from virtual_labs.shared.group_namespace import make_project_group_name
from virtual_labs.shared.saga import SagaCompensator
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.usecases import accounting as accounting_cases


async def _make_kc_group_compensation(
    group: CreatedGroup,
) -> Callable[[], Awaitable[None]]:
    """Build a saga undo that deletes a single Keycloak group.

    `async def` to match the surrounding KC-touching surface. Call
    sites `await` this and push the returned callable onto the
    `SagaCompensator`.
    """

    async def _undo() -> None:
        try:
            await KeycloakRealm.a_delete_group(group_id=group["id"])
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to delete KC group {group['id']}: {exc}")

    return _undo


def _log_orphan_project_account(
    virtual_lab_id: UUID4, project_id: UUID4
) -> Callable[[], Awaitable[None]]:
    async def _undo() -> None:
        logger.warning(
            f"Orphan accounting project account for vlab {virtual_lab_id} "
            f"project {project_id}; no delete endpoint — reconcile manually."
        )

    return _undo


async def _retrieve_group_user_ids(group_id: str) -> list[str]:
    members = await KeycloakRealm.a_get_group_members(group_id=group_id)
    return [UserRepresentation(**member).id for member in members]


async def create_new_project_use_case(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    payload: ProjectCreationBody,
    auth: tuple[AuthUser, str],
    expand: list[ProjectCreateExpand] | None = None,
) -> ProjectCreateOut:
    project_id: UUID4 = uuid4()
    user_id = get_user_id_from_auth(auth)
    requested = set(expand or [])

    try:
        virtual_lab = (
            await session.scalars(
                select(VirtualLab).where(
                    VirtualLab.id == virtual_lab_id,
                    VirtualLab.deleted.is_(False),
                )
            )
        ).one()
        owned_count = (
            await session.scalar(
                select(func.count(Project.id)).where(
                    Project.deleted.is_(False),
                    Project.owner_id == user_id,
                )
            )
        ) or 0
        name_clash = (
            await session.scalar(
                select(func.count(Project.id)).where(
                    Project.virtual_lab_id == virtual_lab_id,
                    func.lower(Project.name) == func.lower(payload.name),
                )
            )
        ) or 0
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="Virtual lab not found",
        )
    except Exception as ex:
        logger.error(f"Project creation preflight failed: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Could not load virtual lab context",
        )

    if name_clash:
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=status.BAD_REQUEST,
            message="Another project with the same name already exists",
        )

    if (
        not virtual_lab.course_template_project_id
        and owned_count >= settings.MAX_PROJECTS_NUMBER
    ):
        raise VliError(
            error_code=VliErrorCode.LIMIT_EXCEEDED,
            http_status_code=status.BAD_REQUEST,
            message=f"You have reached the maximum limit of {settings.MAX_PROJECTS_NUMBER} projects",
        )

    # external provisioning (KC + accounting)
    comp = SagaCompensator()

    try:
        admin_group_name = make_project_group_name(
            virtual_lab_id, project_id, UserRoleEnum.admin
        )
        member_group_name = make_project_group_name(
            virtual_lab_id, project_id, UserRoleEnum.member
        )
        admin_group_id, member_group_id, vlab_admin_users = await asyncio.gather(
            KeycloakRealm.a_create_group(
                {"name": admin_group_name},
            ),
            KeycloakRealm.a_create_group(
                {"name": member_group_name},
            ),
            _retrieve_group_user_ids(
                group_id=str(virtual_lab.admin_group_id),
            ),
        )
        assert admin_group_id is not None
        assert member_group_id is not None
        admin_group: CreatedGroup = {"id": admin_group_id, "name": admin_group_name}
        member_group: CreatedGroup = {"id": member_group_id, "name": member_group_name}
        # Register teardowns immediately after the resources exist
        comp.push(await _make_kc_group_compensation(admin_group))
        comp.push(await _make_kc_group_compensation(member_group))

        # Attach the requesting user, then any vlab admins, to the
        # new project's admin group
        # Run member-side attach concurrently with admin attaches when applicable
        attach_tasks: list[Awaitable[object]] = [
            KeycloakRealm.a_group_user_add(
                user_id=user_id,
                group_id=admin_group["id"],
            )
        ]
        # Attach the requester to the member group if they're not already a
        # vlab admin
        if vlab_admin_users and str(user_id) not in vlab_admin_users:
            attach_tasks.append(
                KeycloakRealm.a_group_user_add(
                    user_id=user_id,
                    group_id=str(
                        virtual_lab.member_group_id,
                    ),
                )
            )
        # Attach vlab admins to the project admin group,
        # but skip if the requester is also a vlab admin
        for admin_uid in vlab_admin_users or []:
            if str(admin_uid) == str(user_id):
                continue
            attach_tasks.append(
                KeycloakRealm.a_group_user_add(
                    user_id=UUID(admin_uid),
                    group_id=admin_group["id"],
                )
            )
        await asyncio.gather(*attach_tasks)
    except AssertionError:
        await comp.compensate(reason="missing group_id from KC")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Admin/Member group_id failed to be generated",
        )
    except KeycloakError as ex:
        await comp.compensate(reason="keycloak error")
        logger.error(f"Keycloak error during project group setup: {ex}")
        raise VliError(
            error_code=ex.response_code or VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="KC Group creation/attaching failed",
        )
    except Exception as ex:
        await comp.compensate(reason="unknown KC error")
        logger.error(f"Error during creating/attaching to group in KC: {ex}")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="KC Group creation/attaching failed",
        )

    if settings.ACCOUNTING_BASE_URL is not None:
        try:
            await accounting_cases.create_project_account(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
                name=payload.name,
            )
            comp.push(_log_orphan_project_account(virtual_lab_id, project_id))
        except Exception as ex:
            logger.error(f"Accounting project account failed: {ex}")
            await comp.compensate(reason="accounting failure")
            raise VliError(
                error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
                http_status_code=status.BAD_GATEWAY,
                message="Project account creation failed",
            )

    expanded_virtual_lab = (
        VirtualLabDetails.model_validate(virtual_lab)
        if ProjectCreateExpand.virtual_lab in requested
        else None
    )

    # DB transaction — close any txn auto-begun by upstream deps or
    # the Phase A preflight reads before starting our explicit one.
    if session.in_transaction():
        await session.commit()

    project_row_snapshot: dict[str, object]
    try:
        async with session.begin():
            project = Project(
                id=project_id,
                name=payload.name,
                description=payload.description,
                contact_email=payload.contact_email,
                virtual_lab_id=virtual_lab_id,
                admin_group_id=admin_group["id"],
                member_group_id=member_group["id"],
                owner_id=user_id,
            )
            session.add(project)
            await session.flush()
            # Snapshot before commit; ORM attrs become stale on commit
            project_row_snapshot = {
                **ProjectSchema.model_validate(project).model_dump(),
                "virtual_lab_id": virtual_lab_id,
            }
    except IntegrityError:
        await comp.compensate(reason="project name conflict")
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=status.BAD_REQUEST,
            message="Project already exists",
        )
    except SQLAlchemyError as ex:
        await comp.compensate(reason="database error")
        logger.exception(f"Database error creating new project: {ex}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Project creation failed",
        )
    except Exception as ex:
        await comp.compensate(reason="unknown DB error")
        logger.exception(f"Unexpected error creating project: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during creating a new project",
        )

    # first-project credit transfer
    # The admin set we already have is sufficient, every vlab admin
    # was just attached to this project's admin group, plus the
    # requesting user. No extra KC round-trip needed.
    project_admins = list({*(vlab_admin_users or []), str(user_id)})

    balance_added = False
    if owned_count == 0 and settings.ACCOUNTING_BASE_URL is not None:
        try:
            balance_response = await accounting_cases.get_virtual_lab_balance(
                virtual_lab_id=virtual_lab_id, include_projects=False
            )
            current_balance = float(balance_response.data.balance)
            if current_balance > 0:
                await accounting_cases.assign_project_budget(
                    virtual_lab_id=virtual_lab_id,
                    project_id=project_id,
                    amount=current_balance,
                )
                balance_added = True
                logger.info(
                    f"Transferred {current_balance} credits to project {project_id}"
                )
        except Exception as ex:  # noqa: BLE001
            logger.error(
                f"Failed to transfer credits to first project {project_id}: {ex}"
            )

    project_out = ProjectCreateOut.model_validate(
        {
            **project_row_snapshot,
            "user_count": len(project_admins),
            "admins": project_admins,
            "balance_added": balance_added
            if ProjectCreateExpand.balance in requested
            else None,
            "virtual_lab": expanded_virtual_lab,
        }
    )

    return project_out
