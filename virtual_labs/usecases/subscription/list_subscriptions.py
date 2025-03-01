from http import HTTPStatus
from typing import Optional, Tuple

from fastapi import HTTPException, Response
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import SubscriptionDetails
from virtual_labs.infrastructure.db.models import SubscriptionStatus
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.subscription_repo import SubscriptionRepository


async def list_subscriptions(
    db: AsyncSession,
    auth: Tuple[AuthUser, str],
    status: Optional[SubscriptionStatus] = None,
) -> Response:
    """
    list subscriptions with optional filtering.

    can filter subscription status.
    """
    try:
        subscription_repo = SubscriptionRepository(db)
        subscriptions = await subscription_repo.list_subscriptions(
            status=status,
        )

        subscription_details = [
            SubscriptionDetails(
                id=sub.id,
                stripe_subscription_id=sub.stripe_subscription_id,
                status=sub.status,
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                amount=sub.amount,
                currency=sub.currency,
                interval=sub.interval,
                auto_renew=sub.auto_renew,
                cancel_at_period_end=sub.cancel_at_period_end,
                canceled_at=sub.canceled_at,
            )
            for sub in subscriptions
        ]

        return VliResponse.new(
            message="Subscriptions retrieved successfully",
            data={"subscriptions": [sub.model_dump() for sub in subscription_details]},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error listing subscriptions: {str(e)}")
        raise VliError(
            message=f"Failed to list subscriptions: {str(e)}",
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
