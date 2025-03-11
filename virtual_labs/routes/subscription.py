from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.payment import PaymentFilter, PaymentListResponse, PaymentType
from virtual_labs.domain.subscription import (
    CancelSubscriptionRequest,
    CreateSubscriptionRequest,
    NextPaymentDateResponse,
    SubscriptionDetails,
    SubscriptionStatusResponse,
    SubscriptionTiersListResponse,
    UserSubscriptionResponse,
    UserSubscriptionsResponse,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import SubscriptionStatus
from virtual_labs.infrastructure.kc.auth import a_verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases.subscription import (
    cancel_subscription_usecase,
    check_user_subscription_usecase,
    create_subscription_usecase,
    get_next_payment_date_usecase,
    get_subscription_usecase,
    get_user_active_subscription_usecase,
    list_payments_usecase,
    list_subscription_tiers_usecase,
    list_subscriptions_usecase,
    list_user_subscriptions_history_usecase,
)

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.post(
    "",
    operation_id="create_subscription",
    summary="Create a new subscription",
    response_model=VliAppResponse[SubscriptionDetails],
)
async def create_subscription(
    payload: CreateSubscriptionRequest,
    db: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    create a new subscription for a virtual lab.

    1. validates the virtual lab exists and user has permission
    2. creates a subscription in Stripe
    3. stores the subscription details in the database
    4. returns the subscription details with payment link

    """
    return await create_subscription_usecase(payload, db, auth)


@router.get(
    "/tiers",
    operation_id="list_subscription_tiers",
    summary="List available subscription tiers",
    response_model=VliAppResponse[SubscriptionTiersListResponse],
)
async def list_subscription_tiers(
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
    db: AsyncSession = Depends(default_session_factory),
) -> Response:
    """
    list all available subscription tiers with pricing information.

    Returns a list of subscription plans
    """
    return await list_subscription_tiers_usecase(auth, db)


@router.delete(
    "",
    operation_id="cancel_subscription",
    summary="Cancel the user's active subscription",
    response_model=VliAppResponse[SubscriptionDetails],
)
async def cancel_subscription(
    payload: CancelSubscriptionRequest,
    db: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    cancel the user's active subscription at the end of the current billing period.
    the subscription will remain active until the end of the paid period.
    """
    return await cancel_subscription_usecase(payload, db, auth)


@router.get(
    "",
    operation_id="list_subscriptions",
    summary="List subscriptions",
    response_model=VliAppResponse[List[SubscriptionDetails]],
)
async def list_subscriptions(
    status: Optional[SubscriptionStatus] = None,
    db: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    list subscriptions with optional filtering.

    can filter by virtual lab ID, user ID, and/or subscription status.
    """
    return await list_subscriptions_usecase(db, auth, status)


@router.get(
    "/payments",
    operation_id="list_payments",
    summary="List payments with filters",
    response_model=VliAppResponse[PaymentListResponse],
)
async def list_payments(
    start_date: Optional[datetime] = Query(
        None, description="filter payments from this date"
    ),
    end_date: Optional[datetime] = Query(
        None, description="filter payments to this date"
    ),
    card_last4: Optional[str] = Query(
        None, description="filter by last 4 digits of card"
    ),
    card_brand: Optional[str] = Query(
        None, description="filter by card brand (e.g. visa, mastercard)"
    ),
    payment_type: Optional[PaymentType] = Query(
        None, description="filter by payment type (subscription or standalone)"
    ),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    list payments with various filters.

    this endpoint allows filtering payments by:
    - Date range (start_date, end_date)
    - Card details (last4, brand)
    - Payment type (subscription or standalone)
    - Virtual lab ID

    the response is paginated with the following information:
    - total_count: Total number of matching payments
    - total_pages: Total number of pages
    - current_page: Current page number
    - page_size: Number of items per page
    - has_next: Whether there is a next page
    - has_previous: Whether there is a previous page
    - payments: List of payment details for the current page
    """

    filters = PaymentFilter(
        start_date=start_date,
        end_date=end_date,
        card_last4=card_last4,
        card_brand=card_brand,
        payment_type=payment_type,
        page=page,
        page_size=page_size,
    )

    return await list_payments_usecase(db, filters, auth)


@router.get(
    "/active",
    operation_id="get_user_active_subscription",
    summary="Get subscription details for a user",
    description="Retrieves details of a user's active subscription including its type (free or paid)",
    response_model=VliAppResponse[UserSubscriptionResponse],
)
async def get_user_subscription(
    db: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    get the current subscription for a specific user.

    Returns details of the subscription along with the 'type' property
    indicating whether it's 'free' or 'paid'.
    """
    return await get_user_active_subscription_usecase(db, auth)


@router.get(
    "/next-payment",
    operation_id="get_next_payment_date",
    summary="Get the next payment date for the current user's paid subscription",
    description="Retrieves the next payment date for the user's active paid subscription",
    response_model=VliAppResponse[NextPaymentDateResponse],
)
async def get_next_payment_date(
    db: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    get the next payment date for a paid subscription.

    For Stripe subscriptions, this is the end date of the current billing period
    unless the subscription is set to be canceled.
    """
    return await get_next_payment_date_usecase(db, auth)


@router.get(
    "/check",
    operation_id="check_user_subscription",
    summary="Check if a user has an active subscription",
    description="Determines whether a user has an active subscription and returns its type (free or paid)",
    response_model=VliAppResponse[SubscriptionStatusResponse],
)
async def check_user_subscription(
    db: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    check if a user has an active subscription.

    Returns information about the existence and type ('free' or 'paid') of the subscription.
    """
    return await check_user_subscription_usecase(db, auth)


@router.get(
    "/history",
    operation_id="list_user_subscriptions_with_payments",
    summary="List all subscriptions of the current user with payment history",
    description="Retrieves all subscriptions (active and inactive) for the authenticated user with detailed payment information",
    response_model=VliAppResponse[UserSubscriptionsResponse],
)
async def list_user_subscriptions_with_payments(
    db: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    list all subscriptions of the authenticated user with their corresponding payments.

    retrieves the complete subscription history for the current user,
    including both active and inactive subscriptions, along with detailed payment
    information for each subscription.
    """
    return await list_user_subscriptions_history_usecase(db, auth)


@router.get(
    "/{subscription_id}",
    operation_id="get_subscription",
    summary="Get subscription details",
    response_model=VliAppResponse[SubscriptionDetails],
)
async def get_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    get details for a specific subscription.

    returns the subscription details including status, billing period, and payment information.
    """
    return await get_subscription_usecase(subscription_id, db, auth)
