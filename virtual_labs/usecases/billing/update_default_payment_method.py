from http import HTTPStatus as status
from typing import Tuple
from uuid import UUID

import stripe
from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.payment_method import PaymentMethod
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.repositories.billing_repo import (
    BillingMutationRepository,
    BillingQueryRepository,
)
from virtual_labs.repositories.labs import get_undeleted_virtual_lab


async def update_default_payment_method(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    payment_method_id: UUID4,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    billing_mut_repo = BillingMutationRepository(session)
    billing_query_repo = BillingQueryRepository(session)

    try:
        vlab = await get_undeleted_virtual_lab(session, virtual_lab_id)
    except SQLAlchemyError as ex:
        logger.error(f"Error during retrieving virtual lab :({ex})")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving virtual lab failed",
        )

    try:
        payment_method = await billing_query_repo.retrieve_payment_method_by_id(
            payment_method_id=payment_method_id,
        )
    except SQLAlchemyError as ex:
        logger.error(f"Error during retrieving db payment method :({ex})")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving payment methods failed",
        )

    try:
        stripe_payment_method = stripe_client.payment_methods.retrieve(
            str(payment_method.stripe_payment_method_id),
        )

    except stripe.StripeError as ex:
        logger.error(f"Error during retrieving stripe payment method :({ex})")
        raise VliError(
            message="Retrieving stripe payment method failed",
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_GATEWAY,
            details=str(ex),
        )

    try:
        stripe_client.customers.update(
            str(vlab.stripe_customer_id),
            {
                "invoice_settings": {
                    "default_payment_method": stripe_payment_method.id
                },
            },
        )
    except stripe.StripeError as ex:
        logger.error(f"Error during update stripe payment method :({ex})")
        raise VliError(
            message="Updating default stripe payment method failed",
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_GATEWAY,
            details=str(ex),
        )
    try:
        update_payment_methods = (
            await billing_mut_repo.update_vl_default_payment_method(
                virtual_lab_id=virtual_lab_id,
                payment_method_id=UUID(str(payment_method.id)),
            )
        )

        return VliResponse.new(
            message="Updating default payment method ended successfully",
            data={
                "virtual_lab_id": virtual_lab_id,
                "payment_methods": [
                    PaymentMethod.model_validate(pm) for pm in update_payment_methods
                ],
            },
        )
    except SQLAlchemyError as ex:
        logger.error(f"Update payment methods db failed ({ex})")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Update payment methods db failed",
        )
    except Exception as ex:
        logger.error(f"Error during updating default payment method ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during updating default payment method",
        )
