from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import (
    SubscriptionDetails,
)
from virtual_labs.infrastructure.db.models import PaidSubscription
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def cancel_subscription(
    db: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    cancel a subscription at the end of the current billing period.
    """
    try:
        user_id = get_user_id_from_auth(auth)
        subscription_repo = SubscriptionRepository(db)
        stripe_service = get_stripe_repository()

        subscription = await subscription_repo.get_active_subscription_by_user_id(
            user_id,
        )

        if not subscription:
            raise VliError(
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
                http_status_code=HTTPStatus.NOT_FOUND,
                message="No active subscription found",
            )

        if isinstance(subscription, PaidSubscription):
            await stripe_service.cancel_subscription(
                subscription.stripe_subscription_id,
                cancel_immediately=False,
            )

            subscription.cancel_at_period_end = True
            subscription.auto_renew = False

            await db.commit()
            await db.refresh(subscription)

        details = SubscriptionDetails(
            id=subscription.id,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            type=subscription.subscription_type,
        )

        return VliResponse.new(
            message="Subscription will be canceled at the end of the billing period",
            data={"subscription": details.model_dump()},
        )

    except Exception as e:
        logger.exception(f"Error canceling subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=f"Failed to cancel subscription: {str(e)}",
        )
