from datetime import datetime
from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import (
    CreateSubscriptionRequest,
    SubscriptionDetails,
)
from virtual_labs.infrastructure.db.models import (
    PaidSubscription,
    SubscriptionStatus,
    SubscriptionType,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


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

    """
    try:
        subscription_repo = SubscriptionRepository(db_session=session)
        stripe_service = get_stripe_repository()

        user_id = get_user_id_from_auth(auth)

        # verify the virtual lab exists and user has permission
        vlab = await get_undeleted_virtual_lab(session, payload.virtual_lab_id)
        if not vlab:
            raise VliError(
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
                http_status_code=HTTPStatus.NOT_FOUND,
                message=f"Virtual lab with ID {payload.virtual_lab_id} not found",
            )

        # check if there's already an active subscription for this lab
        existing_active_subscription = (
            await subscription_repo.get_active_subscription_by_lab_id(
                payload.virtual_lab_id
            )
        )

        if existing_active_subscription:
            raise VliError(
                error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
                http_status_code=HTTPStatus.CONFLICT,
                message="This virtual lab already has an active subscription",
            )

        stripe_subscription = await stripe_service.create_subscription(
            customer_id=vlab.stripe_customer_id,
            price_id=payload.price_id,
            payment_method_id=payload.payment_method_id,
            metadata={
                "virtual_lab_id": str(payload.virtual_lab_id),
                "user_id": str(user_id),
                "entity": str(vlab.entity),
                "email": str(vlab.reference_email),
            },
        )

        if not stripe_subscription:
            raise VliError(
                error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
                http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                message="Failed to create subscription in Stripe",
            )

        subscription = PaidSubscription()
        subscription.user_id = user_id
        subscription.virtual_lab_id = payload.virtual_lab_id
        subscription.type = "paid"
        subscription.subscription_type = SubscriptionType.PRO

        subscription.stripe_subscription_id = str(
            getattr(stripe_subscription, "id", "")
        )
        subscription.stripe_price_id = payload.price_id
        subscription.customer_id = vlab.stripe_customer_id
        subscription.status = SubscriptionStatus(
            getattr(stripe_subscription, "status", "incomplete")
        )

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
    except Exception as e:
        logger.error(f"Error creating subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=f"Failed to create subscription: {str(e)}",
        )
