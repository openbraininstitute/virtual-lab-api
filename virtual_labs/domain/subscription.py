from datetime import datetime
from typing import Dict, List, Optional, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field

from virtual_labs.infrastructure.db.models import (
    Subscription,
    SubscriptionStatus,
)


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


class SubscriptionDetailsDict(TypedDict):
    """Type definition for subscription details dictionary"""

    id: UUID
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    type: str


class SubscriptionDetails(BaseModel):
    """
    subscription details
    """

    id: UUID = Field(..., description="subscription id")
    status: SubscriptionStatus = Field(..., description="current subscription status")
    current_period_start: datetime = Field(
        ..., description="start of current billing period"
    )
    current_period_end: datetime = Field(
        ..., description="end of current billing period"
    )
    type: str = Field(..., description="either free or paid")
    # amount: Optional[int] = Field(..., description="subscription amount in cents")
    # currency: Optional[str] = Field(..., description="subscription currency")
    # interval: Optional[str] = Field(
    #     ..., description="billing interval ('month', 'year')"
    # )

    # cancel_at_period_end: Optional[bool] = Field(
    #     None,
    #     description="whether the subscription will be canceled at the end of the current period",
    # )
    # canceled_at: Optional[datetime] = Field(
    #     None, description="when the subscription was canceled, if applicable"
    # )

    @classmethod
    def from_subscription(cls, subscription: Subscription) -> "SubscriptionDetails":
        """Convert a Subscription model to SubscriptionDetails"""
        subscription_dict: SubscriptionDetailsDict = {
            "id": subscription.id,
            "status": subscription.status,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "type": subscription.subscription_type,
            # "amount": getattr(subscription, "amount", 0),
            # "currency": getattr(subscription, "currency", None),
            # "interval": getattr(subscription, "interval", None),
            # "cancel_at_period_end": getattr(
            #     subscription, "cancel_at_period_end", None
            # ),
            # "canceled_at": getattr(subscription, "canceled_at", None),
        }

        return cls(**subscription_dict)


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
