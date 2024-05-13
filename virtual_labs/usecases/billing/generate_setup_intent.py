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
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.repositories.labs import get_undeleted_virtual_lab


async def generate_setup_intent(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    auth: Tuple[AuthUser, str],
) -> Response:
    try:
        vlab = await get_undeleted_virtual_lab(session, virtual_lab_id)

        setup_intent = stripe_client.setup_intents.create(
            {
                "customer": str(vlab.stripe_customer_id),
                "payment_method_types": ["card"],
                "metadata": {
                    "virtual_lab_id": str(virtual_lab_id),
                },
            }
        )

        return VliResponse.new(
            message="Setup intent generated successfully",
            data={
                "id": setup_intent.id,
                "client_secret": setup_intent.client_secret,
                "customer_id": str(vlab.stripe_customer_id),
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Fetching virtual lab failed",
        )
    except stripe.StripeError as ex:
        logger.error(f"Error during creating stripe setup intent :({ex})")
        raise VliError(
            message="Creating stripe intent failed",
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_GATEWAY,
            details=str(ex),
        )
    except Exception as ex:
        logger.error(f"Error during generating setup intent ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during generating setup intent",
        )
