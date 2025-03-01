from typing import Tuple

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.payment import (
    PaymentDetails,
    PaymentFilter,
    PaymentListResponse,
    PaymentType,
)
from virtual_labs.infrastructure.db.models import SubscriptionPayment
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.payment_repo import PaymentRepository


def _is_standalone_payment(payment: SubscriptionPayment) -> bool:
    return payment.standalone


async def list_payments(
    session: AsyncSession,
    filters: PaymentFilter,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    List payments with filters.

    This use case allows filtering payments by:
    - Date range (start_date, end_date)
    - Card details (last4, brand)
    - Payment type (subscription or standalone)
    - Virtual lab ID

    Returns a paginated list of payments with their details.
    """
    payment_repo = PaymentRepository(session)

    # Get payments from repository
    payments, total_count = await payment_repo.list_payments(filters)

    # Calculate pagination details
    total_pages = (total_count + filters.page_size - 1) // filters.page_size
    has_next = filters.page < total_pages
    has_previous = filters.page > 1

    # Convert to response model
    payment_details = []
    for payment in payments:
        details = PaymentDetails(
            id=payment.id,
            amount_paid=payment.amount_paid,
            currency=payment.currency,
            status=payment.status,
            payment_date=payment.payment_date,
            payment_type=PaymentType.STANDALONE
            if _is_standalone_payment(payment)
            else PaymentType.SUBSCRIPTION,
            card_brand=payment.card_brand,
            card_last4=payment.card_last4,
            card_exp_month=payment.card_exp_month,
            card_exp_year=payment.card_exp_year,
            cardholder_name=payment.cardholder_name,
            cardholder_email=payment.cardholder_email,
            receipt_url=payment.receipt_url,
            invoice_pdf=payment.invoice_pdf,
            subscription_id=getattr(payment, "subscription_id", None),
            period_start=getattr(payment, "period_start", None),
            period_end=getattr(payment, "period_end", None),
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )
        payment_details.append(details)

    response = PaymentListResponse(
        total_count=total_count,
        total_pages=total_pages,
        current_page=filters.page,
        page_size=filters.page_size,
        has_next=has_next,
        has_previous=has_previous,
        payments=payment_details,
    )

    return VliResponse.new(
        message="Payments retrieved successfully",
        data=response.model_dump(),
    )
