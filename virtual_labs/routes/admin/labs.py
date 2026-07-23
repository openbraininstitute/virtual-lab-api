from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

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
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants
from virtual_labs.routes.admin.deps import PLATFORM_ADMIN_TAG_PREFIX, platform_admin
from virtual_labs.usecases.admin import labs as admin_labs

router = APIRouter(tags=[f"{PLATFORM_ADMIN_TAG_PREFIX} | Labs"])


@router.get(
    "/labs",
    response_model=PaginatedResponse[AdminVirtualLabDetails],
    summary="List all virtual labs across the platform",
)
async def list_labs(
    params: Annotated[AdminLabsListQuery, Query()],
    session: AsyncSession = Depends(default_session_factory),
) -> PaginatedResponse[AdminVirtualLabDetails]:
    return await admin_labs.list_labs(session, params)


@router.get(
    "/labs/{lab_id}",
    response_model=AdminVirtualLabDetails,
    summary="Get any virtual lab by id, including soft-deleted ones",
)
async def get_lab(
    lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
) -> AdminVirtualLabDetails:
    return await admin_labs.get_lab(session, lab_id)


@router.get(
    "/labs/{lab_id}/users",
    response_model=LabResponse[VirtualLabUsers],
    summary="List members of any virtual lab",
)
async def get_lab_users(
    lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
) -> LabResponse[VirtualLabUsers]:
    return LabResponse[VirtualLabUsers](
        message="Users for virtual lab",
        data=await admin_labs.get_lab_users(session, lab_id),
    )


@router.get(
    "/labs/{lab_id}/invites",
    response_model=list[AdminLabInviteDetails],
    summary="List pending invites of any virtual lab",
)
async def get_lab_invites(
    lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
) -> list[AdminLabInviteDetails]:
    return await admin_labs.get_lab_invites(session, lab_id)


@router.patch(
    "/labs/{lab_id}",
    response_model=LabResponse[VirtualLabOut],
    summary="Update any virtual lab",
    dependencies=[Depends(platform_admin)],
)
async def update_lab(
    lab_id: UUID4,
    payload: VirtualLabUpdate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> LabResponse[VirtualLabOut]:
    updated = await admin_labs.update_lab(session, lab_id, payload, actor=auth[0])
    return LabResponse[VirtualLabOut](message="Updated virtual lab", data=updated)


@router.delete(
    "/labs/{lab_id}",
    response_model=LabResponse[VirtualLabOut],
    summary="Soft-delete any virtual lab",
    dependencies=[Depends(platform_admin)],
)
async def delete_lab(
    lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> LabResponse[VirtualLabOut]:
    deleted = await admin_labs.delete_lab(session, lab_id, actor=auth[0], token=auth[1])
    return LabResponse[VirtualLabOut](message="Deleted virtual lab", data=deleted)


@router.patch(
    "/labs/{lab_id}/users/{user_id}/role",
    response_model=LabResponse[VirtualLabUser],
    summary="Change a member's role in any virtual lab",
    dependencies=[Depends(platform_admin)],
)
async def change_lab_user_role(
    lab_id: UUID4,
    user_id: UUID4,
    new_role: Annotated[UserRoleEnum, Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> LabResponse[VirtualLabUser]:
    return await admin_labs.change_lab_user_role(
        session, lab_id, user_id, new_role, actor=auth[0]
    )


@router.delete(
    "/labs/{lab_id}/users/{user_id}",
    response_model=LabResponse[None],
    summary="Remove a member from any virtual lab",
    dependencies=[Depends(platform_admin)],
)
async def remove_lab_user(
    lab_id: UUID4,
    user_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> LabResponse[None]:
    await admin_labs.remove_lab_user(session, lab_id, user_id, actor=auth[0])
    return LabResponse[None](message="User removed from virtual lab", data=None)


@router.delete(
    "/labs/{lab_id}/invites/{invite_id}",
    response_model=LabResponse[None],
    summary="Cancel a pending invite of any virtual lab",
    dependencies=[Depends(platform_admin)],
)
async def cancel_lab_invite(
    lab_id: UUID4,
    invite_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> LabResponse[None]:
    await admin_labs.cancel_lab_invite(session, lab_id, invite_id, actor=auth[0])
    return LabResponse[None](message="Invite cancelled", data=None)
