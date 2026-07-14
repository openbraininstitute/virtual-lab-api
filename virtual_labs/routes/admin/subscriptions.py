from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.admin import (
    AdminSubscriptionDetails,
    AdminSubscriptionsListQuery,
)
from virtual_labs.domain.common import PaginatedResponse
from virtual_labs.domain.subscription import CancelSubscriptionRequest
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants
from virtual_labs.routes.admin.deps import PLATFORM_ADMIN_TAG_PREFIX, platform_admin
from virtual_labs.usecases.admin import subscriptions as admin_subscriptions

router = APIRouter(tags=[f"{PLATFORM_ADMIN_TAG_PREFIX} | Subscriptions"])


@router.get(
    "/subscriptions",
    response_model=PaginatedResponse[AdminSubscriptionDetails],
    summary="List all subscriptions across the platform",
)
async def list_subscriptions(
    params: Annotated[AdminSubscriptionsListQuery, Query()],
    session: AsyncSession = Depends(default_session_factory),
) -> PaginatedResponse[AdminSubscriptionDetails]:
    return await admin_subscriptions.list_subscriptions(session, params)


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=AdminSubscriptionDetails,
    summary="Get any subscription by id",
)
async def get_subscription(
    subscription_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
) -> AdminSubscriptionDetails:
    return await admin_subscriptions.get_subscription(session, subscription_id)


@router.post(
    "/subscriptions/{subscription_id}/cancel",
    summary="Cancel any active paid subscription at period end",
    dependencies=[Depends(platform_admin)],
)
async def cancel_subscription(
    subscription_id: UUID4,
    payload: CancelSubscriptionRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> Response:
    return await admin_subscriptions.cancel_subscription(
        session, subscription_id, payload, actor=auth[0]
    )
