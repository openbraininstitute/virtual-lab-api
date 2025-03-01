from http import HTTPStatus
from typing import Tuple
from uuid import UUID

from fastapi import HTTPException, Response
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import SubscriptionDetails
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.subscription_repo import SubscriptionRepository


async def get_subscription(
    subscription_id: UUID,
    db: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    Get details for a specific subscription.

    Returns the subscription details including status, billing period, and payment information.
    """
    try:
        # Get subscription from database
        subscription_repo = SubscriptionRepository(db)
        subscription = await subscription_repo.get_subscription_by_id(subscription_id)

        if not subscription:
            raise VliError(
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
                http_status_code=HTTPStatus.NOT_FOUND,
                message=f"Subscription with ID {subscription_id} not found",
            )

        details = SubscriptionDetails(
            id=subscription.id,
            stripe_subscription_id=subscription.stripe_subscription_id,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            amount=subscription.amount,
            currency=subscription.currency,
            interval=subscription.interval,
            auto_renew=subscription.auto_renew,
            cancel_at_period_end=subscription.cancel_at_period_end,
            canceled_at=subscription.canceled_at,
        )

        return VliResponse.new(
            message="Subscription details retrieved successfully",
            data={"subscription": details.model_dump()},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch subscription: {str(e)}",
        )
