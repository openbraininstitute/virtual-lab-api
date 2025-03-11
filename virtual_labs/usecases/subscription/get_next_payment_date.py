from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.infrastructure.db.models import PaidSubscription
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def get_next_payment_date(
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    get the next payment date for a user's paid subscription.

    retrieves the user's active subscription and returns
    the next billing date, which is the current_period_end date for
    active Stripe subscriptions.

    Args:
        db: database session
        auth: Auth header

    Returns:
        Response: A response containing the next payment date information
    """
    try:
        user_id = get_user_id_from_auth(auth)
        subscription_repo = SubscriptionRepository(db_session=session)

        # Get the user's active subscription
        subscription = await subscription_repo.get_active_subscription_by_user_id(
            user_id
        )

        if not subscription:
            raise ValueError(f"No active subscription found for user {user_id}")

        if not isinstance(subscription, PaidSubscription):
            raise ValueError("User's subscription is not a paid subscription")

        await session.refresh(subscription)

        # For paid subscriptions, the next payment date is the end of the current period
        # unless the subscription is being canceled at the end of the period
        if subscription.cancel_at_period_end:
            return VliResponse.new(
                message="Subscription will be canceled at the end of the current period",
                data={
                    "subscription_id": str(subscription.id),
                    "next_payment_date": None,
                    "current_period_end": subscription.current_period_end,
                },
            )
        else:
            return VliResponse.new(
                message="Next payment date retrieved successfully",
                data={
                    "subscription_id": str(subscription.id),
                    "next_payment_date": subscription.current_period_end,
                    "current_period_end": subscription.current_period_end,
                },
            )
    except ValueError as e:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=str(e),
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error while fetching next payment date: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to fetch next payment date due to database error",
        )
    except Exception as e:
        logger.error(f"Unexpected error while fetching next payment date: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An unexpected error occurred while fetching the next payment date",
        )
