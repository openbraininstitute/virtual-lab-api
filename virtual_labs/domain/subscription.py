from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, TypedDict, Union
from uuid import UUID

from pydantic import BaseModel, Field

from virtual_labs.infrastructure.db.models import (
    Subscription,
    SubscriptionStatus,
    SubscriptionType,
)


class StandalonePaymentResponse(BaseModel):
    """
    Response model for standalone payments
    """

    amount: float = Field(..., description="Amount paid in dollars")
    currency: str = Field(..., description="Currency code (e.g., 'usd')")
    status: str = Field(..., description="Payment status")
    receipt_url: Optional[str] = Field(None, description="URL to payment receipt")
    card_last4: str = Field(..., description="Last 4 digits of the card")
    card_brand: str = Field(..., description="Card brand used for payment")


class IntervalType(str, Enum):
    """
    Enum representing billing interval types.
    """

    MONTH = "month"
    YEAR = "year"


class PriceOption(BaseModel):
    """
    a price option for a subscription plan.
    """

    id: str = Field(..., description="stripe price id")
    amount: int = Field(..., description="price amount in cents")
    discount: int = Field(..., description="discount in cents")
    currency: str = Field(..., description="price currency (e.g., 'chf')")
    interval: IntervalType = Field(..., description="billing interval (month or year)")
    nickname: Optional[str] = Field(None, description="price nickname")


class SubscriptionTier(BaseModel):
    """
    a subscription plan that users can subscribe to.
    """

    id: str = Field(..., description="stripe product id")
    name: str = Field(..., description="plan name")
    description: Optional[str] = Field(None, description="plan description")
    prices: List[PriceOption] = Field(
        ..., description="list of available price options (monthly, yearly)"
    )
    currency: str = Field(..., description="currency of the plan")
    sanity_id: Optional[str] = Field(None, description="sanity id for the plan")
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

    tier_id: UUID = Field(..., description="app tier id")
    interval: IntervalType = Field(..., description="billing interval (month or year)")
    payment_method_id: str = Field(
        ..., description="stripe payment method id to use for billing"
    )
    metadata: Optional[Dict[str, str]] = Field(
        default_factory=dict, description="additional metadata for the subscription"
    )


class UserSubscriptionResponse(BaseModel):
    """
    Response model for the get_user_subscription endpoint.
    """

    subscription: Dict[
        str, Union[str, UUID, SubscriptionStatus, datetime, bool, None]
    ] = Field(..., description="Details of the user's subscription")


class NextPaymentDateResponse(BaseModel):
    """
    Response model for the get_next_payment_date endpoint.
    """

    subscription_id: str = Field(..., description="ID of the subscription")
    next_payment_date: Optional[datetime] = Field(
        None, description="Next payment date, null if subscription will be canceled"
    )
    current_period_end: datetime = Field(
        ..., description="End date of the current billing period"
    )


class SubscriptionStatusResponse(BaseModel):
    """
    Response model for the check_user_subscription endpoint.
    """

    has_subscription: bool = Field(
        ..., description="Whether the user has an active subscription"
    )
    subscription_id: Optional[str] = Field(
        None, description="ID of the subscription if exists"
    )
    type: Optional[str] = Field(
        None, description="Type of subscription: 'free' or 'paid'"
    )
    subscription_type: Optional[SubscriptionType] = Field(
        ..., description="subscription type (free, pro, premium)"
    )
    status: Optional[str] = Field(None, description="Status of the subscription")
    current_period_end: Optional[datetime] = Field(
        None, description="End date of the current billing period"
    )


class SubscriptionPaymentItem(BaseModel):
    """
    Details of a payment for a subscription
    """

    id: UUID = Field(..., description="Payment ID")
    amount_paid: int = Field(..., description="Amount paid in cents")
    currency: str = Field(..., description="Currency code (e.g., 'usd')")
    status: str = Field(..., description="Payment status")
    payment_date: datetime = Field(..., description="Date of payment")
    card_brand: str = Field(..., description="Card brand used for payment")
    card_last4: str = Field(..., description="Last 4 digits of the card")
    invoice_pdf: Optional[str] = Field(None, description="URL to invoice PDF")
    receipt_url: Optional[str] = Field(None, description="URL to payment receipt")
    period_start: datetime = Field(..., description="Start of billing period")
    period_end: datetime = Field(..., description="End of billing period")


class UserSubscriptionAndPaymentsHistory(BaseModel):
    """
    User subscription with its payments
    """

    id: UUID = Field(..., description="Subscription ID")
    type: str = Field(..., description="Subscription type (free or paid)")
    subscription_type: SubscriptionType = Field(..., description="")
    status: SubscriptionStatus = Field(..., description="Current subscription status")
    current_period_start: datetime = Field(..., description="Start of current period")
    current_period_end: datetime = Field(..., description="End of current period")
    created_at: datetime = Field(..., description="When the subscription was created")
    cancel_at_period_end: Optional[bool] = Field(
        None, description="Whether the subscription will be canceled at period end"
    )
    total_paid: float = Field(
        0.0, description="Total amount paid for this subscription"
    )
    payments: List[SubscriptionPaymentItem] = Field(
        default_factory=list, description="Payments for this subscription"
    )


class UserSubscriptionsResponse(BaseModel):
    """
    Response model for listing a user's subscriptions with payments
    """

    subscriptions: List[UserSubscriptionAndPaymentsHistory] = Field(
        ..., description="List of user's subscriptions with payments"
    )
    total_paid: float = Field(
        ..., description="Total amount paid across all subscriptions"
    )
    total_subscriptions: int = Field(
        ..., description="Total number of subscriptions in history"
    )


class SubscriptionTiersListResponse(BaseModel):
    tiers: List[SubscriptionTier]


class CancelSubscriptionRequest(BaseModel):
    reason: str = Field(..., description="reason for canceling subscription")
