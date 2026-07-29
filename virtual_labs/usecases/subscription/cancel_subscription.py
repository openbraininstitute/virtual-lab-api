"""Cancel a paid subscription at the end of the current billing period.

Same shape as `create_subscription`:

  1. Validate the local state under a single short transaction.
  2. Make the Stripe write *outside* any DB transaction.
  3. Persist the synchronous local state under a second transaction
     and build the response DTO before the block exits.

Stripe's `customer.subscription.updated` webhook will arrive shortly
afterwards and reconcile the local row with the live remote state.
The synchronous response is best-effort; the webhook is the
eventual source of truth.

`subscriptions.update(cancel_at_period_end=True)` is naturally
idempotent — calling it twice in a row sets the same flag without
side effects — so we don't need a Stripe idempotency key here.
"""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from fastapi import Response
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import (
    EntityNotFound,
    SubscriptionAlreadyCanceled,
    SubscriptionNotActive,
)
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.subscription import (
    CancelSubscriptionRequest,
    SubscriptionDetails,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.infrastructure.stripe import helpers as stripe_helpers
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def cancel_subscription(
    payload: CancelSubscriptionRequest,
    session: AsyncSession,
    auth: tuple[AuthUser, str],
) -> Response:
    """Mark the requester's active paid subscription for cancellation
    at period end."""
    return await cancel_subscription_for_user(
        payload, session, user_id=get_user_id_from_auth(auth)
    )


async def cancel_subscription_for_user(
    payload: CancelSubscriptionRequest,
    session: AsyncSession,
    *,
    user_id: UUID,
    expected_subscription_id: UUID | None = None,
) -> Response:
    """Cancellation core, keyed on the *target* user rather than the
    requester — the platform-admin flow cancels on behalf of another
    user. `expected_subscription_id` guards the admin path: when set,
    the user's active paid subscription must be that exact row.
    """
    try:
        subscription_repo = SubscriptionRepository(session)
        stripe_service = get_stripe_repository()

        # validate state, snapshot the Stripe id
        async with session.begin():
            stripe_subscription_id = await _validate_and_snapshot_stripe_id(
                subscription_repo, user_id, expected_subscription_id
            )

        # Stripe write outside any DB transaction so the connection
        # isn't held across the network round-trip.
        canceled_subscription = await stripe_service.cancel_subscription(
            stripe_subscription_id, cancel_immediately=False
        )

        # persist the synchronous local state and build the
        # response DTO before the block exits. Reading ORM attributes
        # after commit would trigger a sync-context lazy-load that
        # fails under asyncpg with `MissingGreenlet`.
        response_details: SubscriptionDetails
        async with session.begin():
            subscription = await subscription_repo.get_active_paid_subscription_locked(
                user_id
            )
            if subscription is None:
                # Race with the webhook (or another cancel), rare but
                # not catastrophic; the Stripe state is already updated
                raise EntityNotFound(message="No active paid subscription found")

            subscription.cancel_at_period_end = bool(
                canceled_subscription.cancel_at_period_end
            )
            canceled_at = stripe_helpers.get_canceled_at(canceled_subscription)
            if canceled_at is not None:
                subscription.canceled_at = canceled_at
            ended_at = stripe_helpers.get_ended_at(canceled_subscription)
            if ended_at is not None:
                subscription.ended_at = ended_at
            subscription.auto_renew = False
            subscription.cancellation_reason = payload.reason
            await session.flush()
            response_details = SubscriptionDetails(
                id=subscription.id,
                status=subscription.status,
                current_period_start=subscription.current_period_start,
                current_period_end=subscription.current_period_end,
                type=subscription.subscription_type,
            )

        return VliResponse.new(
            message="Subscription will be canceled at the end of the billing period",
            data={"subscription": response_details.model_dump()},
        )

    except SubscriptionAlreadyCanceled:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Subscription has already been canceled",
        )
    except SubscriptionNotActive:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Subscription is not active",
        )
    except EntityNotFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="No active paid subscription found",
        )
    except VliError:
        raise
    except Exception:
        logger.exception("Unexpected error canceling subscription")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to cancel subscription",
        )


async def _validate_and_snapshot_stripe_id(
    subscription_repo: SubscriptionRepository,
    user_id: UUID,
    expected_subscription_id: UUID | None = None,
) -> str:
    """Return the Stripe subscription id for the user's active paid sub.

    Raises the appropriate domain exception when the subscription is
    missing, already cancel-flagged, or no longer active. The string
    return value is a primitive, safe to read after the surrounding
    `session.begin()` commits and expires ORM attributes.
    """
    subscription = await subscription_repo.get_active_paid_subscription_locked(user_id)
    if subscription is None:
        raise EntityNotFound(message="No active paid subscription found")
    if (
        expected_subscription_id is not None
        and subscription.id != expected_subscription_id
    ):
        raise SubscriptionNotActive(
            message="Subscription is not the user's active paid subscription"
        )
    if subscription.cancel_at_period_end:
        raise SubscriptionAlreadyCanceled(
            message="Subscription has already been canceled"
        )
    if subscription.canceled_at:
        raise SubscriptionNotActive(message="Subscription is not currently active")
    return str(subscription.stripe_subscription_id)
