"""Create a new project inside an existing virtual lab."""

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
from virtual_labs.core.ledger import Ledger, ledger_container
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
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.infrastructure.kc.models import (
    CreatedGroup,
    UserRepresentation,
)
from virtual_labs.infrastructure.settings import settings
from virtual_labs.shared.group_namespace import make_project_group_name
from virtual_labs.usecases import accounting as accounting_cases


async def _make_kc_group_compensation(
    group: CreatedGroup,
) -> Callable[[], Awaitable[None]]:
    """Build a saga undo that deletes a single Keycloak group.

    `async def` to match the surrounding KC-touching surface. Call
    sites `await` this and push the returned callable onto the
    `Ledger`.
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


async def ensure_unique_name_within_virtual_lab(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    project_name: str,
) -> None:
    try:
        name_clash = (
            await session.scalar(
                select(func.count(Project.id)).where(
                    Project.virtual_lab_id == virtual_lab_id,
                    func.lower(Project.name) == func.lower(project_name),
                )
            )
        ) or 0
    except Exception as ex:
        logger.error(f"Project name uniqueness check failed: {ex}")
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


async def ensure_virtual_lab_exists(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
) -> VirtualLab:
    try:
        return (
            await session.scalars(
                select(VirtualLab).where(
                    VirtualLab.id == virtual_lab_id,
                    VirtualLab.deleted.is_(False),
                )
            )
        ).one()
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="Virtual lab not found",
        )
    except Exception as ex:
        logger.error(f"Virtual lab lookup failed: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Could not load virtual lab context",
        )


async def ensure_allow_creation_by_count_restriction(
    session: AsyncSession,
    *,
    virtual_lab: VirtualLab,
    user_id: UUID,
) -> int:
    try:
        owned_count = (
            await session.scalar(
                select(func.count(Project.id)).where(
                    Project.deleted.is_(False),
                    Project.owner_id == user_id,
                )
            )
        ) or 0
    except Exception as ex:
        logger.error(f"Project count restriction check failed: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Could not load virtual lab context",
        )

    if not virtual_lab.course and owned_count >= settings.MAX_PROJECTS_NUMBER:
        raise VliError(
            error_code=VliErrorCode.LIMIT_EXCEEDED,
            http_status_code=status.BAD_REQUEST,
            message=f"You have reached the maximum limit of {settings.MAX_PROJECTS_NUMBER} projects",
        )

    return owned_count


async def ensure_group_creation(
    *,
    vlab_admin_group_id: str,
    vlab_member_group_id: str,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    user_id: UUID,
    comp: Ledger,
) -> tuple[CreatedGroup, CreatedGroup, list[str]]:
    # NB: the parent vlab's group ids are passed in as primitives, not read
    # off a `VirtualLab` ORM instance. The caller rolls back its read-only
    # transaction before invoking us, which expires ORM attributes — touching
    # one here would trigger a lazy DB refresh outside the async greenlet and
    # raise `greenlet_spawn has not been called`.
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
                group_id=vlab_admin_group_id,
            ),
        )
        assert admin_group_id is not None
        assert member_group_id is not None
        admin_group: CreatedGroup = {"id": admin_group_id, "name": admin_group_name}
        member_group: CreatedGroup = {"id": member_group_id, "name": member_group_name}
        comp.push(await _make_kc_group_compensation(admin_group))
        comp.push(await _make_kc_group_compensation(member_group))

        # The requester owns the new project, so they must be a project admin.
        # Additional memberships are batched below and executed together.
        attach_tasks: list[Awaitable[object]] = [
            KeycloakRealm.a_group_user_add(
                user_id=user_id,
                group_id=admin_group["id"],
            )
        ]
        # Non-vlab-admin requesters also need virtual-lab member access so the
        # project remains visible through the parent virtual lab membership.
        if vlab_admin_users and str(user_id) not in vlab_admin_users:
            attach_tasks.append(
                KeycloakRealm.a_group_user_add(
                    user_id=user_id,
                    group_id=vlab_member_group_id,
                )
            )
        # every existing virtual-lab admin inherits admin access to the project
        # skip the requester if they are already a vlab admin; they were added
        # as the project owner in the first attachment task
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
        return admin_group, member_group, vlab_admin_users
    # compensation is driven by the enclosing `ledger_container` scope: any
    # undo already pushed onto `comp` is unwound automatically when these
    # errors propagate. We only classify the failure into a `VliError`
    except AssertionError:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Admin/Member group_id failed to be generated",
        )
    except KeycloakError as ex:
        logger.error(f"Keycloak error during project group setup: {ex}")
        raise VliError(
            error_code=ex.response_code or VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="KC Group creation/attaching failed",
        )
    except Exception as ex:
        logger.error(f"Error during creating/attaching to group in KC: {ex}")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="KC Group creation/attaching failed",
        )


async def ensure_accounting_initialization(
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    project_name: str,
    comp: Ledger,
) -> None:
    if settings.ACCOUNTING_BASE_URL is None:
        return

    try:
        await accounting_cases.create_project_account(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            name=project_name,
        )
        comp.push(_log_orphan_project_account(virtual_lab_id, project_id))
    except Exception as ex:
        # Unwinding is handled by the enclosing `ledger_container`; just
        # classify the failure.
        logger.error(f"Accounting project account failed: {ex}")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_GATEWAY,
            message="Project account creation failed",
        )


async def create_project_record(
    session: AsyncSession,
    *,
    project_id: UUID4,
    virtual_lab_id: UUID4,
    payload: ProjectCreationBody,
    admin_group: CreatedGroup,
    member_group: CreatedGroup,
    user_id: UUID,
) -> dict[str, object]:
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
            return {
                **ProjectSchema.model_validate(project).model_dump(),
                "virtual_lab_id": virtual_lab_id,
            }
    except IntegrityError:
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=status.BAD_REQUEST,
            message="Project already exists",
        )
    except SQLAlchemyError as ex:
        logger.exception(f"Database error creating new project: {ex}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Project creation failed",
        )
    except Exception as ex:
        logger.exception(f"Unexpected error creating project: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during creating a new project",
        )


async def seed_initial_project_budget(
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    owned_count: int,
) -> bool:
    """Best-effort first-project budget transfer.

    This runs after the local project row has committed. Keep the
    signature primitive-only so SQLAlchemy cannot lazy-load expired ORM
    attributes after commit, which would fail under asyncpg with
    `MissingGreenlet`.
    """

    if owned_count != 0 or settings.ACCOUNTING_BASE_URL is None:
        return False

    try:
        balance_response = await accounting_cases.get_virtual_lab_balance(
            virtual_lab_id=virtual_lab_id, include_projects=False
        )
        current_balance = float(balance_response.data.balance)
        if current_balance <= 0:
            return False

        await accounting_cases.assign_project_budget(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            amount=current_balance,
        )
        logger.info(f"Transferred {current_balance} credits to project {project_id}")
        return True
    except Exception as ex:  # noqa: BLE001
        logger.error(f"Failed to transfer credits to first project {project_id}: {ex}")
        return False


async def create_new_project_use_case(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    payload: ProjectCreationBody,
    auth: tuple[AuthUserGrants, str],
    expand: list[ProjectCreateExpand] | None = None,
) -> ProjectCreateOut:
    user_id = auth[0].id
    requested = set(expand or [])
    project_draft_id: UUID4 = uuid4()

    await ensure_unique_name_within_virtual_lab(
        session,
        virtual_lab_id=virtual_lab_id,
        project_name=payload.name,
    )
    virtual_lab = await ensure_virtual_lab_exists(
        session,
        virtual_lab_id=virtual_lab_id,
    )
    expanded_virtual_lab = (
        VirtualLabDetails.model_validate(virtual_lab)
        if ProjectCreateExpand.virtual_lab in requested
        else None
    )
    owned_count = await ensure_allow_creation_by_count_restriction(
        session,
        virtual_lab=virtual_lab,
        user_id=user_id,
    )

    vlab_admin_group_id = str(virtual_lab.admin_group_id)
    vlab_member_group_id = str(virtual_lab.member_group_id)

    # release the read-only transaction held by the pre-checks above before
    # opening the write transaction inside `create_project_record`, we roll
    # back (never commit) so none of the caller's earlier work is flushed
    await session.rollback()

    # external provisioning + persistence run under a ledger scope: if any
    # step raises, every undo recorded so far is unwound in LIFO order
    # automatically, so a future error path can't forget to compensate
    async with ledger_container() as comp:
        admin_group, member_group, vlab_admin_users = await ensure_group_creation(
            vlab_admin_group_id=vlab_admin_group_id,
            vlab_member_group_id=vlab_member_group_id,
            virtual_lab_id=virtual_lab_id,
            project_id=project_draft_id,
            user_id=user_id,
            comp=comp,
        )

        await ensure_accounting_initialization(
            virtual_lab_id=virtual_lab_id,
            project_id=project_draft_id,
            project_name=payload.name,
            comp=comp,
        )

        project_row_snapshot = await create_project_record(
            session,
            project_id=project_draft_id,
            virtual_lab_id=virtual_lab_id,
            payload=payload,
            admin_group=admin_group,
            member_group=member_group,
            user_id=user_id,
        )

    # post-commit: Only
    if not virtual_lab.course:
        await seed_initial_project_budget(
            virtual_lab_id=virtual_lab_id,
            project_id=project_draft_id,
            owned_count=owned_count,
        )

    project_admins = list({*(vlab_admin_users or []), str(user_id)})

    project_out = ProjectCreateOut.model_validate(
        {
            **project_row_snapshot,
            "user_count": len(project_admins),
            "admins": project_admins,
            "virtual_lab": expanded_virtual_lab,
        }
    )

    return project_out
