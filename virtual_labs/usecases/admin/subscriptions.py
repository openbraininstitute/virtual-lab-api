"""Platform-admin operations over subscriptions."""

from http import HTTPStatus

from fastapi import Response
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.admin import (
    AdminSubscriptionDetails,
    AdminSubscriptionsListQuery,
)
from virtual_labs.domain.common import PaginatedResponse
from virtual_labs.domain.subscription import CancelSubscriptionRequest
from virtual_labs.infrastructure.db.models import Subscription
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.usecases.admin._audit import log_admin_action
from virtual_labs.usecases.subscription.cancel_subscription import (
    cancel_subscription_for_user,
)


def _details(subscription: Subscription) -> AdminSubscriptionDetails:
    return AdminSubscriptionDetails(
        id=subscription.id,
        status=subscription.status,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        type=subscription.subscription_type,
        user_id=subscription.user_id,
        virtual_lab_id=subscription.virtual_lab_id,
        tier=subscription.tier.tier.value if subscription.tier else None,
    )


async def list_subscriptions(
    session: AsyncSession, params: AdminSubscriptionsListQuery
) -> PaginatedResponse[AdminSubscriptionDetails]:
    rows, total = await SubscriptionRepository(session).admin_list_subscriptions(
        user_id=params.user_id,
        virtual_lab_id=params.virtual_lab_id,
        status=params.status,
        subscription_type=params.subscription_type,
        offset=params.offset,
        limit=params.page_size,
    )
    return PaginatedResponse.build(
        items=[_details(subscription) for subscription in rows],
        total=total,
        page=params.page,
        size=params.page_size,
    )


async def get_subscription(
    session: AsyncSession, subscription_id: UUID4
) -> AdminSubscriptionDetails:
    subscription = await SubscriptionRepository(
        session
    ).get_subscription_by_id_with_tier(subscription_id)
    if subscription is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Subscription not found",
        )
    return _details(subscription)


async def cancel_subscription(
    session: AsyncSession,
    subscription_id: UUID4,
    payload: CancelSubscriptionRequest,
    actor: AuthUserGrants,
) -> Response:
    subscription = await SubscriptionRepository(session).get_subscription_by_id(
        subscription_id
    )
    if subscription is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Subscription not found",
        )
    # snapshot before the cancellation core commits and expires the row
    target_user_id = subscription.user_id

    response = await cancel_subscription_for_user(
        payload,
        session,
        user_id=target_user_id,
        expected_subscription_id=subscription_id,
    )
    log_admin_action(
        actor,
        "subscription.cancel",
        "subscription",
        subscription_id,
        target_user_id=target_user_id,
        reason=payload.reason,
    )
    return response
