from http import HTTPStatus
from typing import Tuple

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.common import PageParams, PaginatedResultsResponse
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.invite_repo import InviteQueryRepository
from virtual_labs.shared.utils.auth import (
    get_user_email_from_auth,
)


async def list_user_pending_virtual_labs(
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
    page_params: PageParams,
) -> PaginatedResultsResponse[VirtualLabDetails]:
    invite_repo = InviteQueryRepository(session=session)
    try:
        user_email = get_user_email_from_auth(auth)
        paginated_results = await invite_repo.get_user_invited_virtual_labs_by_email(
            email=user_email,
            page_params=page_params,
        )

        labs = [
            VirtualLabDetails.model_validate(lab).model_copy(
                update={"invite_id": invite_id}
            )
            for lab, invite_id in paginated_results.rows
        ]

        return PaginatedResultsResponse(
            total=paginated_results.count,
            page=page_params.page,
            page_size=len(paginated_results.rows),
            results=labs,
        )
    except Exception as e:
        logger.exception(e)
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=f"Error retrieving virtual labs: {e}",
        )
