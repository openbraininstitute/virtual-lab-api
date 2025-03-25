from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import SubscriptionStatusResponse
from virtual_labs.infrastructure.db.models import (
    PaidSubscription,
    SubscriptionType,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def check_user_subscription(
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    check if a user has an active subscription.

    determines whether a user has an active subscription,
    and if so, what type of subscription it is.

    Args:
        db: database session
        auth: Auth header

    Returns:
        Response: A response containing information about the user's subscription status
    """
    try:
        user_id = get_user_id_from_auth(auth)
        subscription_repo = SubscriptionRepository(db_session=session)
        subscription = await subscription_repo.get_active_subscription_by_user_id(
            user_id,
        )

        if not subscription:
            return VliResponse.new(
                message="User does not have an active paid subscription",
                data=SubscriptionStatusResponse(
                    has_subscription=False,
                    subscription_id=None,
                    current_period_end=None,
                    subscription_type=None,
                    type=None,
                    status=None,
                ).model_dump(),
            )

        subscription_type_str = (
            "paid" if isinstance(subscription, PaidSubscription) else "free"
        )

        return VliResponse.new(
            message="User subscription status retrieved successfully",
            data=SubscriptionStatusResponse(
                has_subscription=True,
                subscription_id=str(subscription.id),
                current_period_end=subscription.current_period_end,
                subscription_type=SubscriptionType(subscription.subscription_type)
                if isinstance(subscription, PaidSubscription)
                else SubscriptionType.FREE,
                type=subscription_type_str,
                status=subscription.status.value,
            ).model_dump(),
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error while checking user subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to check user subscription due to database error",
        )
    except Exception as e:
        logger.error(f"Unexpected error while checking user subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An unexpected error occurred while checking the user subscription",
        )
