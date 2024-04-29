from pydantic import UUID4

from virtual_labs.infrastructure.db.models import Project
from virtual_labs.repositories.user_repo import UserQueryRepository


def is_user_in_project(user_id: UUID4, project: Project) -> bool:
    """Returns true if the user is either the member or the admin of the project. Otherwise returns False."""
    user_repo = UserQueryRepository()
    if user_repo.is_user_in_group(
        user_id=user_id, group_id=str(project.admin_group_id)
    ) or user_repo.is_user_in_group(
        user_id=user_id, group_id=str(project.member_group_id)
    ):
        return True
    return False
