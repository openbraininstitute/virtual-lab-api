from http import HTTPStatus as status
from typing import Tuple, cast

import stripe
from fastapi.responses import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import (
    EntityNotCreated,
    EntityNotFound,
)
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.repositories.stripe_user_repo import (
    StripeUserMutationRepository,
    StripeUserQueryRepository,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth, get_user_metadata


async def generate_setup_intent(
    session: AsyncSession,
    *,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    Generate a Stripe setup intent for adding payment methods.

    This function:
    1. Checks if the user has a Stripe customer ID
    2. Creates a Stripe customer if one doesn't exist
    3. Creates a setup intent for the customer

    Args:
        session: Database session
        auth: Authentication tuple containing user info and token

    Returns:
        Response: A response containing the setup intent details
    """
    try:
        auth_user, _ = auth
        user_id = get_user_id_from_auth(auth)
        user_metadata = get_user_metadata(auth_user)

        stripe_user_repo = StripeUserQueryRepository(db_session=session)
        mutation_repo = StripeUserMutationRepository(db_session=session)

        stripe_user = await stripe_user_repo.get_by_user_id(user_id)

        if not stripe_user:
            customer = await stripe_client.customers.create_async(
                {
                    "email": auth_user.email,
                    "name": auth_user.name,
                    "metadata": user_metadata,
                }
            )

            stripe_user = await mutation_repo.create(user_id, customer.id)

            if not stripe_user:
                raise EntityNotCreated

            customer_id = customer.id
        else:
            customer_id = cast(str, stripe_user.stripe_costumer_id)

        if customer_id:
            setup_intent = await stripe_client.setup_intents.create_async(
                {
                    "customer": customer_id,
                    "payment_method_types": ["card"],
                    "metadata": {
                        **user_metadata,
                    },
                }
            )
        else:
            raise EntityNotFound

        return VliResponse.new(
            message="Setup intent generated successfully",
            data={
                "id": setup_intent.id,
                "client_secret": setup_intent.client_secret,
                "customer_id": customer_id,
            },
        )
    except EntityNotFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Customer id is required",
        )
    except EntityNotCreated:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Failed to save Stripe customer details",
        )
    except SQLAlchemyError as ex:
        logger.error(f"Database error: {ex}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Database operation failed",
            details=str(ex),
        )
    except stripe.StripeError as ex:
        logger.error(f"Error during creating stripe setup intent: {ex}")
        raise VliError(
            message="Creating stripe intent failed",
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_GATEWAY,
            details=str(ex),
        )
    except Exception as ex:
        logger.error(f"Error during generating setup intent: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during generating setup intent",
            details=str(ex),
        )
