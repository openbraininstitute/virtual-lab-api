from http import HTTPStatus
from typing import Dict, List, Tuple

from fastapi import HTTPException, Response
from loguru import logger
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import PriceOption, SubscriptionPlan
from virtual_labs.infrastructure.db.models import (
    SubscriptionPlan as SubscriptionPlanModel,
)
from virtual_labs.infrastructure.kc.models import AuthUser


def create_price_option(
    price_id: str, amount: int, currency: str, interval: str, name: str
) -> PriceOption:
    """
    Helper function to create a PriceOption object.

    Args:
        price_id: The Stripe price ID
        amount: The price amount
        currency: The currency code
        interval: The billing interval (e.g., 'month', 'year')
        name: The name of the subscription plan

    Returns:
        PriceOption: The created PriceOption object
    """
    return PriceOption(
        id=price_id,
        amount=amount,
        currency=currency,
        interval=interval,
        nickname=f"{name} ({interval.capitalize()})",
    )


async def list_subscription_plans(
    auth: Tuple[AuthUser, str],
    db: AsyncSession,
) -> Response:
    """
    list all available subscription plans with pricing information.

    this function retrieves all active subscription plans from the database
    and formats them according to the SubscriptionPlan domain model.

    Args:
        auth: Authentication tuple containing user info and token
        db: Database session

    Returns:
        Response: A response containing a list of subscription plans
    """
    try:
        query = select(SubscriptionPlanModel).where(
            SubscriptionPlanModel.active == true()
        )
        result = await db.execute(query)
        subscription_plan_models = result.scalars().all()

        subscription_plans: List[SubscriptionPlan] = []

        for plan_model in subscription_plan_models:
            price_options: List[PriceOption] = []

            if plan_model.stripe_monthly_price_id and plan_model.monthly_amount > 0:
                price_options.append(
                    create_price_option(
                        plan_model.stripe_monthly_price_id,
                        plan_model.monthly_amount,
                        plan_model.currency,
                        "month",
                        plan_model.name,
                    )
                )

            # Add yearly price if available
            if plan_model.stripe_yearly_price_id and plan_model.yearly_amount > 0:
                price_options.append(
                    create_price_option(
                        plan_model.stripe_yearly_price_id,
                        plan_model.yearly_amount,
                        plan_model.currency,
                        "year",
                        plan_model.name,
                    )
                )

            metadata: Dict[str, str] = {}
            if plan_model.features:
                metadata.update(
                    {f"feature_{k}": str(v) for k, v in plan_model.features.items()}
                )
            if plan_model.plan_metadata:
                metadata.update(
                    {k: str(v) for k, v in plan_model.plan_metadata.items()}
                )

            plan = SubscriptionPlan(
                id=str(plan_model.id),
                name=plan_model.name,
                description=plan_model.description or "",
                prices=price_options,
                metadata=metadata,
                currency=plan_model.currency,
                sanity_id=plan_model.sanity_id,
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
