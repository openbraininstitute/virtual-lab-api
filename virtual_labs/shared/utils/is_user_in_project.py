from pydantic import UUID4

from virtual_labs.infrastructure.db.models import Project
from virtual_labs.repositories.user_repo import UserQueryRepository


async def is_user_in_project(user_id: UUID4, project: Project) -> bool:
    user_repo = UserQueryRepository()
    is_admin = await user_repo.is_user_in_group(
        user_id=user_id, group_id=str(project.admin_group_id)
    )

    is_member = await user_repo.is_user_in_group(
        user_id=user_id, group_id=str(project.member_group_id)
    )

    return is_admin or is_member
