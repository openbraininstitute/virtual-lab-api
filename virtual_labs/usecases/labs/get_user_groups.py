from typing import List, Tuple
from uuid import UUID

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserGroup, UserRoleEnum
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.labs import get_virtual_lab_soft
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def get_user_virtual_lab_groups(
    session: AsyncSession, virtual_lab_id: UUID, auth: Tuple[AuthUser, str]
) -> Response:
    """
    Get the user groups for a virtual lab
    """
    user_id = get_user_id_from_auth(auth)

    # Get the lab and verify it exists
    lab = await get_virtual_lab_soft(session, lab_id=virtual_lab_id)
    if not lab:
        return VliResponse.new(
            message="Virtual lab not found",
            data={"groups": []},
        )

    # Get the user groups from Keycloak
    group_repo = GroupQueryRepository()
    user_groups = await group_repo.a_retrieve_user_groups(user_id=str(user_id))

    # Filter for virtual lab groups
    vlab_admin_group_id = str(lab.admin_group_id)
    vlab_member_group_id = str(lab.member_group_id)

    # Check if user is an admin or member of this virtual lab
    user_vlab_groups: List[UserGroup] = []
    for group in user_groups:
        if group.id == vlab_admin_group_id:
            user_vlab_groups.append(
                UserGroup(
                    group_id=group.id,
                    name=group.name,
                    group_type="vlab",
                    virtual_lab_id=str(virtual_lab_id),
                    project_id=None,
                    role=UserRoleEnum.admin,
                )
            )
        elif group.id == vlab_member_group_id:
            user_vlab_groups.append(
                UserGroup(
                    group_id=group.id,
                    name=group.name,
                    group_type="vlab",
                    virtual_lab_id=str(virtual_lab_id),
                    project_id=None,
                    role=UserRoleEnum.member,
                )
            )

    return VliResponse.new(
        message="User groups for virtual lab",
        data={"groups": user_vlab_groups},
    )
