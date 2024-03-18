from pydantic import UUID4

from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.repositories.user_repo import UserQueryRepository


def is_user_in_lab(user_id: UUID4, lab: VirtualLab) -> bool:
    """Returns true if the user is either the member or the admin of the lab. Otherwise returns False."""
    user_repo = UserQueryRepository()
    if user_repo.is_user_in_group(
        user_id=user_id, group_id=str(lab.admin_group_id)
    ) or user_repo.is_user_in_group(user_id=user_id, group_id=str(lab.member_group_id)):
        return True
    return False


def is_user_admin_of_lab(user_id: UUID4, lab: VirtualLab) -> bool:
    user_repo = UserQueryRepository()
    if user_repo.is_user_in_group(user_id=user_id, group_id=str(lab.admin_group_id)):
        return True
    return False
