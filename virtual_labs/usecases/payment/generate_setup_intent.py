"""Create a Stripe SetupIntent for adding payment methods.

Single side effect: ensure a Stripe customer exists for the user
(via `StripeCustomerService`, transaction-aware) and create a
SetupIntent against it
"""

from __future__ import annotations

from http import HTTPStatus

import stripe
from fastapi.responses import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import EntityNotCreated
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.services.stripe_customer import (
    StripeCustomerCreationError,
    StripeCustomerService,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth, get_user_metadata


async def generate_setup_intent(
    session: AsyncSession,
    *,
    auth: tuple[AuthUser, str],
) -> Response:
    """Return a fresh `client_secret` the frontend can use to attach
    a card to the user's Stripe customer."""
    try:
        user_id = get_user_id_from_auth(auth)
        user = get_user_metadata(auth_user=auth[0])

        async with session.begin():
            customer_id, _ = await StripeCustomerService(
                session
            ).ensure_customer_for_user(
                user_id,
                email=user["email"],
                name=user["full_name"],
            )

        setup_intent = await stripe_client.setup_intents.create_async(
            params={
                "customer": customer_id,
                "payment_method_types": ["card"],
                "metadata": {
                    "user_id": str(user_id),
                    "email": user.get("email", ""),
                },
            },
        )

        return VliResponse.new(
            message="Setup intent generated successfully",
            data={
                "id": setup_intent.id,
                "client_secret": setup_intent.client_secret,
                "customer_id": customer_id,
            },
        )

    except (StripeCustomerCreationError, EntityNotCreated):
        logger.exception("Failed to ensure Stripe customer for setup intent")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_CREATED,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Failed to set up payment with payment provider",
        )
    except SQLAlchemyError:
        logger.exception("Database error while generating setup intent")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Database operation failed",
        )
    except stripe.StripeError:
        logger.exception("Stripe error while generating setup intent")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Failed to create Stripe setup intent",
        )
    except VliError:
        raise
    except Exception:
        logger.exception("Unexpected error generating setup intent")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to generate setup intent",
        )
