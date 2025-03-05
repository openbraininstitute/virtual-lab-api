from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.payment import (
    PaymentDetails,
    PaymentFilter,
    PaymentListResponse,
    PaymentType,
)
from virtual_labs.infrastructure.db.models import SubscriptionPayment
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.labs import get_user_virtual_lab
from virtual_labs.repositories.payment_repo import PaymentRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


def _is_standalone_payment(payment: SubscriptionPayment) -> bool:
    return payment.standalone


async def list_payments(
    session: AsyncSession,
    filters: PaymentFilter,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    list payments with filters.

    This use case allows filtering payments by:
    - Date range (start_date, end_date)
    - Card details (last4, brand)
    - Payment type (subscription or standalone)
    - Virtual lab id

    returns a paginated list of payments with their details.
    """
    user_id = get_user_id_from_auth(auth)

    print("ᦨ #  list_payments.py:46 #  user_id:", user_id)

    try:
        payment_repo = PaymentRepository(session)
        virtual_lab = await get_user_virtual_lab(
            db=session,
            owner_id=user_id,
        )

        if virtual_lab is None:
            raise ValueError("No virtual lab for this user")

        payments, total_count = await payment_repo.list_payments(
            virtual_lab.stripe_customer_id,
            filters,
        )

        total_pages = (total_count + filters.page_size - 1) // filters.page_size
        has_next = filters.page < total_pages
        has_previous = filters.page > 1

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
                receipt_url=payment.receipt_url,
                invoice_pdf=payment.invoice_pdf,
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

    except SQLAlchemyError as e:
        logger.error(f"Database error while fetching payments: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to fetch payments due to database error",
        )
    except ValueError as e:
        logger.error("No virtual lab for this user")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error while processing payments: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An unexpected error occurred while processing payments",
        )
