from http import HTTPStatus

from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import LabResponse
from virtual_labs.domain.user import AllUsersCount
from virtual_labs.repositories.user_repo import UserQueryRepository


async def get_count_of_all_users() -> LabResponse[AllUsersCount]:
    try:
        user_repo = UserQueryRepository()
        return LabResponse(
            message="Total users in BBP",
            data=AllUsersCount(total=user_repo.get_all_users_count()),
        )
    except Exception as error:
        logger.warning(f"Error when retrieving total users {error}")
        raise VliError(
            message="Error when retrieving total users",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
        )
