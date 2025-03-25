from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import SubscriptionDetails
from virtual_labs.infrastructure.db.models import PaidSubscription
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def get_user_active_subscription(
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    get the current subscription for a specific user.

    retrieves the user's active subscription and adds information
    about whether it's a free or paid subscription.

    Args:
        user_id: user id
        db: database session
        auth: Auth header

    Returns:
        Response: A response containing the subscription details
    """
    try:
        user_id = get_user_id_from_auth(auth)
        subscription_repo = SubscriptionRepository(db_session=session)
        subscription = await subscription_repo.get_active_subscription_by_user_id(
            user_id
        )

        if not subscription:
            return VliResponse.new(
                message="No user subscription retrieved",
                data=None,
            )

        await session.refresh(subscription)
        details = SubscriptionDetails.from_subscription(subscription)

        subscription_type = (
            "paid" if isinstance(subscription, PaidSubscription) else "free"
        )

        subscription_data = details.model_dump()
        subscription_data["type"] = subscription_type

        if isinstance(subscription, PaidSubscription):
            paid_sub = subscription
            subscription_data.update(
                {
                    "tier": subscription.subscription_type,
                    "cancel_at_period_end": paid_sub.cancel_at_period_end,
                    "next_billing_date": paid_sub.current_period_end,
                    "canceled_at": paid_sub.canceled_at,
                }
            )

        return VliResponse.new(
            message="User subscription details retrieved successfully",
            data={"subscription": subscription_data},
        )
    except ValueError as e:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=str(e),
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error while fetching user subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to fetch user subscription due to database error",
        )
    except Exception as e:
        logger.error(f"Unexpected error while fetching user subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An unexpected error occurred while fetching the user subscription",
        )
