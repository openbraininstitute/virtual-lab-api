from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from virtual_labs.infrastructure.db.models import SubscriptionStatus


class PriceOption(BaseModel):
    """
    a price option for a subscription plan.
    """

    id: str = Field(..., description="stripe price id")
    amount: int = Field(..., description="price amount in cents")
    currency: str = Field(..., description="price currency (e.g., 'chf')")
    interval: str = Field(..., description="billing interval (e.g., 'month', 'year')")
    nickname: Optional[str] = Field(None, description="price nickname")


class SubscriptionPlan(BaseModel):
    """
    a subscription plan that users can subscribe to.
    """

    id: str = Field(..., description="stripe product id")
    name: str = Field(..., description="plan name")
    description: Optional[str] = Field(None, description="plan description")
    prices: List[PriceOption] = Field(
        ..., description="list of available price options (monthly, yearly)"
    )
    metadata: Dict[str, str] = Field(
        default_factory=dict, description="additional metadata about the plan"
    )


class SubscriptionDetails(BaseModel):
    """
    subscription details
    """

    id: UUID = Field(..., description="subscription id")
    stripe_subscription_id: str = Field(..., description="stripe subscription id")
    status: SubscriptionStatus = Field(..., description="current subscription status")
    current_period_start: datetime = Field(
        ..., description="start of current billing period"
    )
    current_period_end: datetime = Field(
        ..., description="end of current billing period"
    )
    amount: int = Field(..., description="subscription amount in cents")
    currency: str = Field(..., description="subscription currency")
    interval: str = Field(..., description="billing interval ('month', 'year')")

    auto_renew: bool = Field(
        ..., description="whether the subscription will automatically renew"
    )
    cancel_at_period_end: Optional[bool] = Field(
        None,
        description="whether the subscription will be canceled at the end of the current period",
    )
    canceled_at: Optional[datetime] = Field(
        None, description="when the subscription was canceled, if applicable"
    )


class CreateSubscriptionRequest(BaseModel):
    """
    create a new subscription payload
    """

    virtual_lab_id: UUID = Field(..., description="id of the virtual lab to subscribe")
    price_id: str = Field(..., description="stripe price id to subscribe to")
    payment_method_id: str = Field(
        ..., description="stripe payment method id to use for billing"
    )
    metadata: Optional[Dict[str, str]] = Field(
        default_factory=dict, description="additional metadata for the subscription"
    )


class CancelSubscriptionRequest(BaseModel):
    """Request model for canceling a subscription"""

    pass
