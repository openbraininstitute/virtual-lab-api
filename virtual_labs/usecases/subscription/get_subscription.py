from http import HTTPStatus
from typing import Tuple
from uuid import UUID

from fastapi import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import SubscriptionDetails
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.subscription_repo import SubscriptionRepository


async def get_subscription(
    subscription_id: UUID,
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    get details for a specific subscription.
    returns the subscription details including status
    """
    try:
        subscription_repo = SubscriptionRepository(db_session=session)
        subscription = await subscription_repo.get_subscription_by_id(subscription_id)

        if not subscription:
            raise ValueError("Subscription not found")

        await session.refresh(subscription)
        details = SubscriptionDetails.from_subscription(subscription)

        return VliResponse.new(
            message="Subscription details retrieved successfully",
            data={"subscription": details.model_dump()},
        )
    except ValueError:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Subscription with id {subscription_id} not found",
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error while fetching subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to fetch subscription due to database error",
        )
    except Exception as e:
        logger.error(f"Unexpected error while fetching subscription: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An unexpected error occurred while fetching the subscription",
        )
