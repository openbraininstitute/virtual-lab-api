from http import HTTPStatus
from typing import Optional, Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import SubscriptionDetails
from virtual_labs.infrastructure.db.models import SubscriptionStatus
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def list_subscriptions(
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
    status: Optional[SubscriptionStatus] = None,
) -> Response:
    """
    list subscriptions with optional filtering.

    can filter subscription status.
    """
    try:
        subscription_repo = SubscriptionRepository(session)
        user_id = get_user_id_from_auth(auth)

        subscriptions = await subscription_repo.list_subscriptions(
            user_id=user_id,
            status=status,
        )

        result = [SubscriptionDetails.from_subscription(sub) for sub in subscriptions]

        return VliResponse.new(
            message="Subscriptions retrieved successfully",
            data={"subscriptions": result},
        )

    except Exception as e:
        logger.exception(f"Error listing subscriptions: {str(e)}")
        raise VliError(
            message=f"Failed to list subscriptions: {str(e)}",
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
