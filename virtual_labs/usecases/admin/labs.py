"""Platform-admin operations over virtual labs.

Reads compose the global repository listing with the same enrichment
the member-scoped endpoints use; mutations delegate to the existing
lab usecases and add an audit log line.
"""

from http import HTTPStatus

from pydantic import UUID4
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.ordering import order_clauses
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.admin import (
    AdminLabInviteDetails,
    AdminLabsListQuery,
    AdminVirtualLabDetails,
)
from virtual_labs.domain.common import PaginatedResponse
from virtual_labs.domain.labs import (
    LabResponse,
    VirtualLabOut,
    VirtualLabUpdate,
    VirtualLabUser,
    VirtualLabUsers,
)
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.repositories import labs as labs_repo
from virtual_labs.repositories.invite_repo import InviteQueryRepository
from virtual_labs.usecases import labs as labs_usecases
from virtual_labs.usecases.admin._audit import log_admin_action
from virtual_labs.usecases.labs._user_labs_helpers import project_counts_by_vlab


async def _enrich(
    session: AsyncSession, rows: list[VirtualLab]
) -> list[AdminVirtualLabDetails]:
    counts = await project_counts_by_vlab(session, [row.id for row in rows])
    return [
        AdminVirtualLabDetails.model_validate(row).model_copy(
            update={"projects_count": counts.get(row.id, 0)}
        )
        for row in rows
    ]


async def list_labs(
    session: AsyncSession, params: AdminLabsListQuery
) -> PaginatedResponse[AdminVirtualLabDetails]:
    rows, total = await labs_repo.admin_list_virtual_labs(
        session,
        query=params.query,
        include_deleted=params.include_deleted,
        deleted_only=params.deleted_only,
        pagination=params,
        order_by=order_clauses(VirtualLab, params.order_by, params.order_direction),
    )
    return PaginatedResponse.build(
        items=await _enrich(session, rows),
        total=total,
        page=params.page,
        size=params.page_size,
    )


async def get_lab(session: AsyncSession, lab_id: UUID4) -> AdminVirtualLabDetails:
    row = await labs_repo.get_virtual_lab_soft(session, lab_id)
    if row is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Virtual lab not found",
        )
    (item,) = await _enrich(session, [row])
    return item


async def get_lab_users(session: AsyncSession, lab_id: UUID4) -> VirtualLabUsers:
    return await labs_usecases.get_virtual_lab_users(session, lab_id)


async def get_lab_invites(
    session: AsyncSession, lab_id: UUID4
) -> list[AdminLabInviteDetails]:
    invites = await InviteQueryRepository(session).get_pending_users_for_lab(lab_id)
    return [AdminLabInviteDetails.model_validate(invite) for invite in invites]


async def update_lab(
    session: AsyncSession,
    lab_id: UUID4,
    payload: VirtualLabUpdate,
    actor: AuthUserGrants,
) -> VirtualLabOut:
    updated = await labs_usecases.update_virtual_lab(
        session, lab_id, lab=payload, user_id=actor.id
    )
    log_admin_action(
        actor,
        "lab.update",
        "virtual_lab",
        lab_id,
        fields=sorted(payload.model_dump(exclude_unset=True)),
    )
    return updated


async def delete_lab(
    session: AsyncSession, lab_id: UUID4, actor: AuthUserGrants, token: str
) -> VirtualLabOut:
    deleted = await labs_usecases.delete_virtual_lab(
        session, lab_id, auth=(actor, token)
    )
    log_admin_action(actor, "lab.delete", "virtual_lab", lab_id)
    return deleted


async def change_lab_user_role(
    session: AsyncSession,
    lab_id: UUID4,
    user_id: UUID4,
    new_role: UserRoleEnum,
    actor: AuthUserGrants,
) -> LabResponse[VirtualLabUser]:
    response = await labs_usecases.change_user_role_for_lab(
        lab_id, user_id=user_id, new_role=new_role, db=session
    )
    log_admin_action(
        actor,
        "lab.user_role.update",
        "virtual_lab",
        lab_id,
        user_id=user_id,
        new_role=new_role.value,
    )
    return response


async def remove_lab_user(
    session: AsyncSession, lab_id: UUID4, user_id: UUID4, actor: AuthUserGrants
) -> None:
    await labs_usecases.remove_user_from_lab(lab_id, user_id=user_id, db=session)
    log_admin_action(actor, "lab.user.remove", "virtual_lab", lab_id, user_id=user_id)


async def cancel_lab_invite(
    session: AsyncSession, lab_id: UUID4, invite_id: UUID4, actor: AuthUserGrants
) -> None:
    try:
        invite = await InviteQueryRepository(session).get_vlab_invite_by_id(invite_id)
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Invite not found",
        )
    if invite.virtual_lab_id != lab_id:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Invite does not belong to this virtual lab",
        )
    await labs_usecases.delete_lab_invite(
        session, lab_id, invite.user_email, UserRoleEnum(invite.role)
    )
    log_admin_action(
        actor, "lab.invite.cancel", "virtual_lab", lab_id, invite_id=invite_id
    )
