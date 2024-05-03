from http import HTTPStatus as status
from typing import Tuple

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.payment_method import PaymentMethod, PaymentMethodCreationBody
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.billing_repo import BillingMutationRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def attach_payment_method_to_virtual_lab(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    payload: PaymentMethodCreationBody,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    billing_mut_repo = BillingMutationRepository(session)
    user_id = get_user_id_from_auth(auth)

    try:
        payment_method = await billing_mut_repo.add_new_payment_method(
            virtual_lab_id=virtual_lab_id,
            brand=payload.brand,
            card_number=payload.last4,
            cardholder_email=payload.email,
            cardholder_name=payload.name,
            customer_id=payload.customerId,
            expire_at=payload.expireAt,
            payment_method_id=payload.paymentMethodId,
            user_id=user_id,
        )

        return VliResponse.new(
            message="Payment method added successfully",
            data={
                "virtual_lab_id": virtual_lab_id,
                "payment_method": PaymentMethod(**payment_method.__dict__),
            },
        )

    except SQLAlchemyError as ex:
        print("ex", ex)
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Payment methods failed",
        )
    except Exception as ex:
        logger.error(f"Error during adding new payment method to virtual lab ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during adding new payment method to virtual lab",
        )
