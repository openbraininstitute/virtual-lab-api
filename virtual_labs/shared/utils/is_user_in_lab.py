from pydantic import UUID4

from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.repositories.user_repo import UserQueryRepository


async def is_user_admin_of_lab(user_id: UUID4, lab: VirtualLab) -> bool:
    user_repo = UserQueryRepository()
    return await user_repo.is_user_in_group(
        user_id=user_id, group_id=str(lab.admin_group_id)
    )


async def is_user_member_of_lab(user_id: UUID4, lab: VirtualLab) -> bool:
    user_repo = UserQueryRepository()
    return await user_repo.is_user_in_group(
        user_id=user_id, group_id=str(lab.member_group_id)
    )


async def is_user_in_lab(user_id: UUID4, lab: VirtualLab) -> bool:
    return await is_user_admin_of_lab(user_id, lab) or await is_user_member_of_lab(
        user_id, lab
    )
