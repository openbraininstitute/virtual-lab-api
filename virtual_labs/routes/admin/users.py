from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.admin import (
    AdminSubscriptionDetails,
    AdminSubscriptionsListQuery,
    AdminUserDetails,
    AdminUsersListQuery,
)
from virtual_labs.domain.common import PaginatedResponse
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.models import UserRepresentation
from virtual_labs.routes.admin.deps import PLATFORM_ADMIN_TAG_PREFIX
from virtual_labs.usecases.admin import subscriptions as admin_subscriptions
from virtual_labs.usecases.admin import users as admin_users

router = APIRouter(tags=[f"{PLATFORM_ADMIN_TAG_PREFIX} | Users"])


@router.get(
    "/users",
    response_model=PaginatedResponse[UserRepresentation],
    summary="Search all realm users",
)
async def list_users(
    params: Annotated[AdminUsersListQuery, Query()],
) -> PaginatedResponse[UserRepresentation]:
    return await admin_users.list_users(params)


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetails,
    summary="Get a user's profile, groups and workspace memberships",
)
async def get_user(
    user_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
) -> AdminUserDetails:
    return await admin_users.get_user(session, user_id)


@router.get(
    "/users/{user_id}/subscriptions",
    response_model=PaginatedResponse[AdminSubscriptionDetails],
    summary="List a user's subscriptions",
)
async def get_user_subscriptions(
    user_id: UUID4,
    params: Annotated[AdminSubscriptionsListQuery, Query()],
    session: AsyncSession = Depends(default_session_factory),
) -> PaginatedResponse[AdminSubscriptionDetails]:
    return await admin_subscriptions.list_subscriptions(
        session, params.model_copy(update={"user_id": user_id})
    )
