from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.payment_method import PaymentMethod
from virtual_labs.repositories.billing_repo import BillingQueryRepository


async def retrieve_virtual_lab_payment_methods(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
) -> Response | VliError:
    billing_query_repo = BillingQueryRepository(session)

    try:
        payment_methods = await billing_query_repo.retrieve_vl_payment_methods(
            virtual_lab_id=virtual_lab_id
        )

        return VliResponse.new(
            message=(
                f"Payment methods for {virtual_lab_id} fetched successfully"
                if bool(payment_methods)
                else f"No payment methods was found for: '{virtual_lab_id}'"
            ),
            data={
                "virtual_lab_id": virtual_lab_id,
                "payment_methods": [
                    PaymentMethod(**pm.__dict__) for pm in payment_methods
                ],
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving payment methods failed",
        )
    except Exception as ex:
        logger.error(f"Error during retrieving virtual lab payment methods ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving virtual lab payment methods",
        )
