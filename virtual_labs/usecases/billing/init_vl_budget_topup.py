from http import HTTPStatus as status
from typing import Tuple

import stripe
from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.repositories.billing_repo import (
    BillingQueryRepository,
)
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
from virtual_labs.shared.utils.billing import amount_to_cent


async def init_vl_budget_topup(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    payment_method_id: UUID4,
    credit: float,
    auth: Tuple[AuthUser, str],
) -> Response:
    billing_query_repo = BillingQueryRepository(session)

    try:
        vlab = await get_undeleted_virtual_lab(session, virtual_lab_id)
    except SQLAlchemyError as ex:
        logger.error(f"Error during retrieving virtual lab :({ex})")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.NOT_FOUND,
            message="Retrieving virtual lab failed",
        )

    try:
        payment_method = await billing_query_repo.retrieve_payment_method_by_id(
            payment_method_id=payment_method_id,
        )
    except SQLAlchemyError as ex:
        logger.error(f"Error during retrieving db payment method :({ex})")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.NOT_FOUND,
            message="Retrieving payment methods failed",
        )

    try:
        stripe_payment_method = await stripe_client.payment_methods.retrieve_async(
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
        payment_intent = await stripe_client.payment_intents.create_async(
            {
                "amount": amount_to_cent(credit),
                "currency": "usd",
                "customer": str(vlab.stripe_customer_id),
                "payment_method": stripe_payment_method.id,
                "confirm": True,
                "return_url": settings.VLAB_ADMIN_PATH.format(
                    settings.DEPLOYMENT_NAMESPACE, virtual_lab_id
                ),
                "metadata": {
                    "vlab": str(virtual_lab_id),
                    "payment_method_id": str(payment_method_id),
                },
            }
        )

        return VliResponse.new(
            message="Processing payment intent ended successfully",
            data={
                "virtual_lab_id": virtual_lab_id,
                "status": payment_intent.status,
                "next_action": payment_intent.next_action,
                "cancellation_reason": payment_intent.cancellation_reason,
            },
        )
    except stripe.StripeError as ex:
        logger.error(f"Error during processing stripe payment intent :({ex})")
        raise VliError(
            message="Process stripe payment method intent failed",
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_GATEWAY,
            details=str(ex),
        )
    except Exception as ex:
        logger.error(f"Error during processing adding new budget amount to vlab ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during processing adding new budget amount to vlab",
        )
