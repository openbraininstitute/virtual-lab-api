from datetime import datetime
from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import (
    EntityAlreadyExists,
    EntityNotCreated,
)
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import (
    CreateSubscriptionRequest,
    IntervalType,
    SubscriptionDetails,
)
from virtual_labs.infrastructure.db.models import (
    PaidSubscription,
    SubscriptionStatus,
    SubscriptionType,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.repositories.stripe_user_repo import (
    StripeUserMutationRepository,
    StripeUserQueryRepository,
)
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth, get_user_metadata


async def create_subscription(
    payload: CreateSubscriptionRequest,
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    create a new subscription for a virtual lab.

    1. validates the virtual lab exists and user has permission
    2. creates a subscription in Stripe
    3. stores the subscription details in the database

    Args:
        payload: create subscription payload
        db: database session
        auth: Auth header
    """
    try:
        subscription_repo = SubscriptionRepository(db_session=session)
        stripe_user_repo = StripeUserQueryRepository(db_session=session)
        stripe_user_mutation_repo = StripeUserMutationRepository(db_session=session)
        stripe_service = get_stripe_repository()

        user_id = get_user_id_from_auth(auth)
        user = get_user_metadata(auth_user=auth[0])

        existing_active_subscription = (
            await subscription_repo.get_active_subscription_by_user_id(user_id, "paid")
        )

        if existing_active_subscription:
            raise EntityAlreadyExists

        customer = await stripe_user_repo.get_by_user_id(user_id)

        if customer is None:
            stripe_customer = await stripe_service.create_customer(
                user_id, user["email"], user["full_name"]
            )
            if stripe_customer is None:
                raise EntityNotCreated

            await stripe_user_mutation_repo.create(
                user_id=user_id,
                stripe_customer_id=stripe_customer.id,
            )
            customer_id = stripe_customer.id
        else:
            assert customer.stripe_costumer_id, "Customer not found"
            customer_id = customer.stripe_costumer_id

        subscription_tier = await subscription_repo.get_subscription_tier_by_id(
            payload.tier_id
        )

        if not subscription_tier:
            raise ValueError("Subscription plan not found")

        price_id = (
            subscription_tier.stripe_monthly_price_id
            if payload.interval == IntervalType.MONTH
            else subscription_tier.stripe_yearly_price_id
        )

        if not price_id:
            raise ValueError("Price ID not found")

        stripe_subscription = await stripe_service.create_subscription(
            customer_id=customer_id,
            price_id=price_id,
            payment_method_id=payload.payment_method_id,
            metadata={
                "user_id": str(user_id),
                "email": user["email"],
                "name": user["full_name"],
            },
        )

        if not stripe_subscription:
            raise EntityNotCreated

        subscription = PaidSubscription()
        subscription.user_id = user_id
        subscription.type = "paid"
        subscription.subscription_type = SubscriptionType.PRO

        subscription.stripe_subscription_id = str(
            getattr(stripe_subscription, "id", "")
        )
        subscription.stripe_price_id = price_id
        subscription.customer_id = customer_id
        stripe_subscription_status = getattr(
            stripe_subscription, "status", "incomplete"
        )
        subscription.status = SubscriptionStatus(stripe_subscription_status)

        current_period_start = getattr(
            stripe_subscription, "current_period_start", None
        )

        if current_period_start is not None:
            subscription.current_period_start = datetime.fromtimestamp(
                float(str(current_period_start))
            )

        current_period_end = getattr(stripe_subscription, "current_period_end", None)
        if current_period_end is not None:
            subscription.current_period_end = datetime.fromtimestamp(
                float(str(current_period_end))
            )

        items_list = []
        if "items" in stripe_subscription and "data" in stripe_subscription["items"]:
            items_list = stripe_subscription["items"]["data"]

        if items_list:
            first_item = items_list[0]
            if hasattr(first_item, "price"):
                price_data = first_item.price
            else:
                price_data = first_item.get("price", {})

            if isinstance(price_data, dict):
                subscription.amount = price_data.get("unit_amount", 0)
                subscription.currency = price_data.get("currency", "chf")

                recurring = price_data.get("recurring", {})
                if recurring:
                    subscription.interval = recurring.get("interval", "month")
            else:
                subscription.amount = getattr(price_data, "unit_amount", 0)
                subscription.currency = getattr(price_data, "currency", "chf")

                recurring = getattr(price_data, "recurring", None)
                if recurring:
                    subscription.interval = getattr(recurring, "interval", "month")

        if stripe_subscription_status != "active":
            await subscription_repo.downgrade_to_free(
                user_id=user_id,
            )
        else:
            await subscription_repo.deactivate_free_subscription(
                user_id=user_id,
            )

        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)

        details = SubscriptionDetails(
            id=subscription.id,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            type=subscription.subscription_type,
        )

        return VliResponse.new(
            message="Subscription created successfully",
            data={"subscription": details.model_dump()},
        )
    except ValueError as e:
        logger.error(f"Error creating subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message=str(e),
        )
    except EntityAlreadyExists:
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
            message="This user already has an active subscription",
        )
    except EntityNotCreated as e:
        logger.error(f"Error creating subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_CREATED,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message=f"Failed to create subscription: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error creating subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=f"Failed to create subscription: {str(e)}",
        )
