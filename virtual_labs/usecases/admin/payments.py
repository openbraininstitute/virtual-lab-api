"""Platform-admin operations over payments.

Payments are keyed by Stripe customer in the member-scoped flow; the
admin listing drops that scope and adds an optional `user_id` filter
resolved through the stripe-user mapping.
"""

from http import HTTPStatus

from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.payment import (
    PaymentDetails,
    PaymentFilter,
    PaymentListResponse,
)
from virtual_labs.repositories.payment_repo import PaymentRepository
from virtual_labs.repositories.stripe_user_repo import StripeUserQueryRepository
from virtual_labs.usecases.subscription.list_payments import payment_to_details


async def list_payments(
    session: AsyncSession,
    filters: PaymentFilter,
    user_id: UUID4 | None = None,
) -> PaymentListResponse:
    customer_id: str | None = None
    if user_id is not None:
        stripe_user = await StripeUserQueryRepository(
            db_session=session
        ).get_by_user_id(user_id=user_id)
        if stripe_user is None or not stripe_user.stripe_customer_id:
            # user never reached Stripe — no payments by definition
            return PaymentListResponse(
                total_count=0,
                total_pages=0,
                current_page=filters.page,
                page_size=filters.page_size,
                has_next=False,
                has_previous=filters.page > 1,
                payments=[],
            )
        customer_id = str(stripe_user.stripe_customer_id)

    payments, total = await PaymentRepository(session).admin_list_payments(
        filters, customer_id
    )
    total_pages = (total + filters.page_size - 1) // filters.page_size
    return PaymentListResponse(
        total_count=total,
        total_pages=total_pages,
        current_page=filters.page,
        page_size=filters.page_size,
        has_next=filters.page < total_pages,
        has_previous=filters.page > 1,
        payments=[payment_to_details(payment) for payment in payments],
    )


async def get_payment(session: AsyncSession, payment_id: UUID4) -> PaymentDetails:
    payment = await PaymentRepository(session).get_payment_by_id(payment_id)
    if payment is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Payment not found",
        )
    return payment_to_details(payment)
