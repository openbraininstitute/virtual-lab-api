from http import HTTPStatus
from typing import Dict, List, Tuple

from fastapi import HTTPException, Response
from loguru import logger
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import (
    IntervalType,
    PriceOption,
    SubscriptionTier,
)
from virtual_labs.infrastructure.db.models import (
    SubscriptionTier as SubscriptionTierModel,
)
from virtual_labs.infrastructure.kc.models import AuthUser


def create_price_option(
    price_id: str,
    amount: int,
    discount: int,
    currency: str,
    interval: IntervalType,
    name: str,
) -> PriceOption:
    """
    Helper function to create a PriceOption object.

    Args:
        price_id: The Stripe price ID
        amount: The price amount
        discount: The discount amount
        currency: The currency code
        interval: The billing interval (IntervalType.MONTH or IntervalType.YEAR)

    Returns:
        PriceOption: The created PriceOption object
    """
    return PriceOption(
        id=price_id,
        amount=amount,
        discount=discount,
        currency=currency,
        interval=interval,
        nickname=f"{name} ({interval.capitalize()})",
    )


async def list_subscription_tiers(
    auth: Tuple[AuthUser, str],
    db: AsyncSession,
) -> Response:
    """
    list all available subscription plans with pricing information.

    this function retrieves all active subscription plans from the database
    and formats them according to the SubscriptionPlan domain model.

    Args:
        auth: Auth header
        db: database session

    Returns:
        Response: A response containing a list of subscription plans
    """
    try:
        query = select(SubscriptionTierModel).where(
            SubscriptionTierModel.active == true()
        )
        result = await db.execute(query)
        subscription_tier_models = result.scalars().all()

        subscription_tiers: List[SubscriptionTier] = []

        for tier_model in subscription_tier_models:
            price_options: List[PriceOption] = []

            if tier_model.stripe_monthly_price_id and tier_model.monthly_amount > 0:
                price_options.append(
                    create_price_option(
                        tier_model.stripe_monthly_price_id,
                        tier_model.monthly_amount,
                        tier_model.monthly_discount,
                        tier_model.currency,
                        IntervalType.MONTH,
                        tier_model.name,
                    )
                )

            if tier_model.stripe_yearly_price_id and tier_model.yearly_amount > 0:
                price_options.append(
                    create_price_option(
                        tier_model.stripe_yearly_price_id,
                        tier_model.yearly_amount,
                        tier_model.yearly_discount,
                        tier_model.currency,
                        IntervalType.YEAR,
                        tier_model.name,
                    )
                )

            metadata: Dict[str, str] = {}
            if tier_model.features:
                metadata.update(
                    {f"feature_{k}": str(v) for k, v in tier_model.features.items()}
                )
            if tier_model.plan_metadata:
                metadata.update(
                    {k: str(v) for k, v in tier_model.plan_metadata.items()}
                )

            tier = SubscriptionTier(
                id=str(tier_model.id),
                name=tier_model.name,
                description=tier_model.description or "",
                prices=price_options,
                metadata=metadata,
                currency=tier_model.currency,
                sanity_id=tier_model.sanity_id,
            )

            subscription_tiers.append(tier)

        return VliResponse.new(
            message="Subscription tiers retrieved successfully",
            data={"tiers": [tier.model_dump() for tier in subscription_tiers]},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching subscription tiers: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch subscription tiers: {str(e)}",
        )
