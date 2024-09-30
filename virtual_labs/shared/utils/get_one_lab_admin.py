from http import HTTPStatus

from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.user import UserWithInviteStatus
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.repositories.group_repo import GroupQueryRepository


async def get_one_lab_admin(lab: VirtualLab) -> UserWithInviteStatus:
    """
    Returns one admin for a virtual lab.
    If there are multiple admins, the one whose username appears first in alphabetical order is returned.
    If there are no admins, an exception is raised
    """
    try:
        group_repo = GroupQueryRepository()
        all_admins = await group_repo.retrieve_group_users(str(lab.admin_group_id))

        assert len(all_admins) >= 1
        all_admins.sort(key=lambda x: x.username)

        return UserWithInviteStatus(
            **all_admins[0].model_dump(),
            invite_accepted=True,
            role=UserRoleEnum.admin,
        )
    except Exception as error:
        logger.error(f"Error when retrieving first admin in lab {lab.id}: {error}")
        raise VliError(
            message="Project admin could not be retrieved",
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
