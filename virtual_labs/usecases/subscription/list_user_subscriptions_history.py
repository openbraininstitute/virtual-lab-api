from http import HTTPStatus
from typing import List, Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import (
    SubscriptionPaymentItem,
    UserSubscriptionAndPaymentsHistory,
    UserSubscriptionsResponse,
)
from virtual_labs.infrastructure.db.models import (
    SubscriptionPayment,
    SubscriptionStatus,
    SubscriptionType,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def list_user_subscriptions_history(
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    list all subscriptions of the authenticated user with their corresponding payments.

    retrieves all subscriptions (both active and inactive) for the
    current user, along with payment details for each subscription.

    Args:
        db: database session
        auth: Auth header
        subscription_type: Optional filter by subscription type ("free" or "paid")

    Returns:
        Response: list of subscriptions with payments
    """
    try:
        user_id = get_user_id_from_auth(auth)
        subscription_repo = SubscriptionRepository(db_session=session)
        subscriptions = await subscription_repo.list_subscriptions(
            user_id=user_id, subscription_type="paid"
        )

        if not subscriptions:
            return VliResponse.new(
                message="No subscriptions found for the user",
                data={
                    "subscriptions": [],
                    "total_paid": 0,
                    "subscription_history_count": 0,
                    "has_active_subscription": False,
                },
            )

        subscription_list: List[UserSubscriptionAndPaymentsHistory] = []
        total_paid_all_subscriptions = 0.0

        for subscription in subscriptions:
            subscription_type_value = SubscriptionType(subscription.subscription_type)
            status_value = SubscriptionStatus(subscription.status.value)

            # Create payment details for this subscription
            payment_stmt = (
                select(SubscriptionPayment)
                .where(SubscriptionPayment.subscription_id == subscription.id)
                .order_by(SubscriptionPayment.payment_date.desc())
            )

            payment_result = await session.execute(payment_stmt)
            payments = payment_result.scalars().all()

            payment_details: List[SubscriptionPaymentItem] = []
            subscription_total_paid = 0.0

            for payment in payments:
                payment_detail = SubscriptionPaymentItem(
                    id=payment.id,
                    amount_paid=payment.amount_paid,
                    currency=payment.currency,
                    status=payment.status.value,
                    payment_date=payment.payment_date,
                    card_brand=payment.card_brand,
                    card_last4=payment.card_last4,
                    invoice_pdf=payment.invoice_pdf,
                    receipt_url=payment.receipt_url,
                    period_start=payment.period_start,
                    period_end=payment.period_end,
                )
                payment_details.append(payment_detail)

                if payment.status.value == "succeeded":
                    payment_amount = payment.amount_paid / 100
                    subscription_total_paid += payment_amount
                    total_paid_all_subscriptions += payment_amount

            # Create subscription with payments
            subscription_with_payments = UserSubscriptionAndPaymentsHistory(
                id=subscription.id,
                type=subscription.type,
                subscription_type=subscription_type_value,
                status=status_value,
                current_period_start=subscription.current_period_start,
                current_period_end=subscription.current_period_end,
                created_at=subscription.created_at,
                cancel_at_period_end=subscription.cancel_at_period_end,
                total_paid=round(subscription_total_paid, 2),
                payments=payment_details,
            )
            subscription_list.append(subscription_with_payments)

        response_data = UserSubscriptionsResponse(
            subscriptions=subscription_list,
            total_paid=round(total_paid_all_subscriptions, 2),
            total_subscriptions=len(subscriptions),
        )

        return VliResponse.new(
            message="User subscriptions retrieved successfully",
            data=response_data.model_dump(),
        )
    except SQLAlchemyError as e:
        logger.exception(f"Database error while listing user subscriptions: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to list user subscriptions due to database error",
        )
    except Exception as e:
        logger.exception(f"Unexpected error while listing user subscriptions: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An unexpected error occurred while listing user subscriptions",
        )
