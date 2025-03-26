from typing import List, Tuple

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserGroup, UserRoleEnum
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def get_all_user_groups(
    session: AsyncSession, auth: Tuple[AuthUser, str]
) -> Response:
    """
    Get all groups the authenticated user is a part of
    """
    user_id = get_user_id_from_auth(auth)

    group_repo = GroupQueryRepository()
    user_groups = await group_repo.a_retrieve_user_groups(user_id=str(user_id))

    result_groups: List[UserGroup] = []

    for group in user_groups:
        group_path = group.path

        # Virtual Lab groups typically follow format "vlab/{vlab_id}/{role}"
        if group_path and "/vlab/" in group_path:
            parts = group_path.split("/")
            if len(parts) >= 3:
                vlab_id = parts[-2]
                role_str = parts[-1]

                role = (
                    UserRoleEnum.admin
                    if role_str.lower() == "admin"
                    else UserRoleEnum.member
                )

                result_groups.append(
                    UserGroup(
                        group_id=group.id,
                        name=group.name,
                        group_type="vlab",
                        virtual_lab_id=vlab_id,
                        project_id=None,
                        role=role,
                    )
                )

        # Project groups typically follow format "proj/{vlab_id}/{project_id}/{role}"
        elif group_path and "/proj/" in group_path:
            parts = group_path.split("/")
            if len(parts) >= 4:
                vlab_id = parts[-3]
                project_id = parts[-2]
                role_str = parts[-1]

                role = (
                    UserRoleEnum.admin
                    if role_str.lower() == "admin"
                    else UserRoleEnum.member
                )

                result_groups.append(
                    UserGroup(
                        group_id=group.id,
                        name=group.name,
                        group_type="project",
                        project_id=project_id,
                        virtual_lab_id=vlab_id,
                        role=role,
                    )
                )

    return VliResponse.new(
        message="All user groups",
        data={"groups": result_groups},
    )
