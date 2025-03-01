from http import HTTPStatus
from typing import Tuple

from fastapi import HTTPException, Response
from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import PriceOption, SubscriptionPlan
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe import get_stripe_repository


async def list_subscription_plans(
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    List all available subscription plans with pricing information.

    Returns a list of subscription plans
    """
    try:
        stripe_service = get_stripe_repository()

        # Fetch all active products with prices from Stripe
        products = await stripe_service.list_products(active=True)

        subscription_plans = []
        for product in products:
            # Get prices for this product
            prices = await stripe_service.list_prices(
                product_id=product["id"], active=True
            )

            if not prices:
                continue

            price_options = []
            for price in prices:
                price_options.append(
                    PriceOption(
                        id=price["id"],
                        amount=price["unit_amount"],
                        currency=price["currency"],
                        interval=price.get("recurring", {}).get("interval", "month"),
                        nickname=price.get("nickname"),
                    )
                )

            plan = SubscriptionPlan(
                id=product["id"],
                name=product["name"],
                description=product.get("description", ""),
                prices=price_options,
            )
            subscription_plans.append(plan)

        return VliResponse.new(
            message="Subscription plans retrieved successfully",
            data={"plans": [plan.model_dump() for plan in subscription_plans]},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching subscription plans: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch subscription plans: {str(e)}",
        )
