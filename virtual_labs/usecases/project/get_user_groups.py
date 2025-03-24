from typing import List, Tuple
from uuid import UUID

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserGroup, UserRoleEnum
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def get_user_project_groups(
    session: AsyncSession,
    virtual_lab_id: UUID,
    project_id: UUID,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    """
    Get the user groups for a project and its parent virtual lab
    """
    user_id = get_user_id_from_auth(auth)

    project_repo = ProjectQueryRepository(session)
    project, vlab = await project_repo.retrieve_one_project_by_id(project_id=project_id)

    if not project or not vlab or str(vlab.id) != str(virtual_lab_id):
        return VliResponse.new(
            message="Project or virtual lab not found",
            data={"groups": []},
        )

    group_repo = GroupQueryRepository()
    user_groups = await group_repo.a_retrieve_user_groups(user_id=str(user_id))

    vlab_admin_group_id = str(vlab.admin_group_id)
    vlab_member_group_id = str(vlab.member_group_id)
    project_admin_group_id = str(project.admin_group_id)
    project_member_group_id = str(project.member_group_id)

    user_groups_list: List[UserGroup] = []

    for group in user_groups:
        if group.id == vlab_admin_group_id:
            user_groups_list.append(
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
            user_groups_list.append(
                UserGroup(
                    group_id=group.id,
                    name=group.name,
                    group_type="vlab",
                    virtual_lab_id=str(virtual_lab_id),
                    project_id=None,
                    role=UserRoleEnum.member,
                )
            )

        # Check project groups
        if group.id == project_admin_group_id:
            user_groups_list.append(
                UserGroup(
                    group_id=group.id,
                    name=group.name,
                    group_type="project",
                    project_id=str(project_id),
                    virtual_lab_id=str(virtual_lab_id),
                    role=UserRoleEnum.admin,
                )
            )
        elif group.id == project_member_group_id:
            user_groups_list.append(
                UserGroup(
                    group_id=group.id,
                    name=group.name,
                    group_type="project",
                    project_id=str(project_id),
                    virtual_lab_id=str(virtual_lab_id),
                    role=UserRoleEnum.member,
                )
            )

    return VliResponse.new(
        message="User groups for project and virtual lab",
        data={"groups": user_groups_list},
    )
