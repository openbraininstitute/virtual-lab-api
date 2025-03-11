from http import HTTPStatus
from typing import Optional, Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import (
    EntityNotCreated,
    EntityNotFound,
)
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.payment import CreateStandalonePaymentRequest
from virtual_labs.domain.subscription import StandalonePaymentResponse
from virtual_labs.infrastructure.db.models import (
    PaymentStatus,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.repositories.stripe_user_repo import (
    StripeUserMutationRepository,
    StripeUserQueryRepository,
)
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth, get_user_metadata


async def create_standalone_payment(
    payload: CreateStandalonePaymentRequest,
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    Create a standalone payment for a user.

    1. Ensures the user has a stripe customer id
    2. creates a payment intent in stripe
    3. confirms the payment
    4. records the payment in the database

    Args:
        payload: Payment details
        session: Database session
        auth: Authentication tuple containing user info and token

    Returns:
        Response: A response containing the payment details
    """
    try:
        user_id = get_user_id_from_auth(auth)
        user = get_user_metadata(auth_user=auth[0])

        stripe_service = get_stripe_repository()
        stripe_user_query_repo = StripeUserQueryRepository(db_session=session)
        stripe_user_mutation_repo = StripeUserMutationRepository(db_session=session)
        subscription_repo = SubscriptionRepository(db_session=session)

        subscription = await subscription_repo.get_active_subscription_by_user_id(
            user_id=user_id
        )
        if not subscription:
            raise EntityNotFound

        customer_id: Optional[str] = None
        stripe_user = await stripe_user_query_repo.get_by_user_id(user_id)
        if stripe_user:
            customer_id = stripe_user.stripe_customer_id
        elif not stripe_user:
            customer = await stripe_service.create_customer(
                user_id=user_id, email=user["email"], name=user["full_name"]
            )
            if customer:
                stripe_user = await stripe_user_mutation_repo.create(
                    user_id=user_id, stripe_customer_id=customer.id
                )
                customer_id = customer.id

        if not customer_id:
            raise EntityNotCreated

        payment_intent = await stripe_service.create_payment_intent(
            amount=payload.amount,
            currency=payload.currency,
            customer_id=customer_id,
            payment_method_id=payload.payment_method_id,
            metadata={
                "user_id": str(user_id),
                "subscription_id": str(subscription.id),
                "standalone": "true",
            },
        )

        payment_method = await stripe_service.get_payment_method(
            payment_method_id=payload.payment_method_id
        )

        charge_id = payment_intent.latest_charge
        receipt_url = None
        if charge_id and isinstance(charge_id, str):
            charge = await stripe_service.get_charge(charge_id=charge_id)
            if charge:
                receipt_url = charge.get("receipt_url", None)

        payment_response = StandalonePaymentResponse(
            amount=payload.amount,
            currency=payload.currency,
            status=PaymentStatus(payment_intent.status),
            receipt_url=receipt_url,
            card_last4=payment_method.get("card", {}).get("last4", "0000"),
            card_brand=payment_method.get("card", {}).get("brand", "unknown"),
        )

        return VliResponse.new(
            message="Payment processed successfully",
            data=payment_response.model_dump(),
        )
    except ValueError as e:
        logger.error(f"Entity not found while creating standalone payment: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Customer not found",
        )
    except EntityNotCreated as e:
        logger.error(f"Entity not created while creating standalone payment: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_CREATED,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Failed to create or retrieve Stripe customer",
        )
    except EntityNotFound as e:
        logger.error(f"Entity not found while creating standalone payment: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Subscription not found",
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error while creating standalone payment: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to create payment due to database error",
        )
    except Exception as e:
        logger.error(f"Unexpected error while creating standalone payment: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=f"An unexpected error occurred: {str(e)}",
        )
