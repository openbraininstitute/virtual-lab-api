"""Create a paid subscription for a user.

The flow does three kinds of work — Stripe round-trips, local DB
writes, and external side effects (Keycloak) — and the previous
version mixed them together inside one big try/except. The shape
here matches the resource-first pattern we already use in the
webhook layer:

  1. Validate inputs and gather everything we need (Stripe + DB
     reads only).
  2. Make Stripe writes with a deterministic idempotency key, so a
     network retry returns the existing subscription rather than
     minting a duplicate.
  3. Open a single DB transaction. Re-check the active-subscription
     invariant under `FOR UPDATE`, build the local row from the
     Stripe response via the same mapping module the webhook uses,
     and queue Keycloak updates onto a `PostCommitActions` for
     after-commit execution.
  4. Run the deferred side effects.

The webhook's `customer.subscription.created` upsert is the safety
net: if anything between the Stripe call and the DB commit fails,
the live Stripe subscription still arrives via webhook and the
upsert handler creates the local row. The synchronous response is
best-effort; the eventual-consistency boundary is the webhook.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from uuid import UUID

import stripe
from fastapi import Response
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import (
    EntityAlreadyExists,
    EntityNotCreated,
)
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.billing import BillingAddress, BillingFlow, TaxStatus
from virtual_labs.domain.subscription import (
    CreateSubscriptionRequest,
    IntervalType,
    SubscriptionDetails,
)
from virtual_labs.infrastructure.db.models import (
    PaidSubscription,
    SubscriptionTierEnum,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.infrastructure.stripe.mapping import (
    SubscriptionMappingError,
    apply_subscription_fields,
    map_stripe_subscription_to_db,
)
from virtual_labs.infrastructure.stripe.types import PostCommitActions, PostCommitRunner
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.services.billing import (
    BillingQuoteService,
    is_tax_enabled_for_country,
    save_billing_address_to_user_profile,
)
from virtual_labs.services.payment_guard import (
    CountryMismatchBlocked,
    ensure_ch_country_match,
)
from virtual_labs.services.stripe_customer import (
    StripeCustomerCreationError,
    StripeCustomerService,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth, get_user_metadata


async def create_subscription(
    payload: CreateSubscriptionRequest,
    session: AsyncSession,
    auth: tuple[AuthUser, str],
) -> Response:
    """Orchestrate paid-subscription creation.

    Steps below are split into helpers for readability and for unit
    testing the pure / pure-ish phases independently of the FastAPI
    surface.
    """
    try:
        user_id = get_user_id_from_auth(auth)
        user = get_user_metadata(auth_user=auth[0])
        tax_enabled = is_tax_enabled_for_country(payload.billing_address.country)

        subscription_repo = SubscriptionRepository(db_session=session)
        stripe_service = get_stripe_repository()
        customer_service = StripeCustomerService(
            session, stripe_repository=stripe_service
        )

        # gather + customer ensure inside one short transaction.
        async with session.begin():
            await _check_no_active_paid_subscription(subscription_repo, user_id)
            tier, price_id, discount_id = await _resolve_tier_and_price(
                subscription_repo, payload
            )
            quote = await _resolve_quote(session, payload, user_id, tax_enabled)
            customer_id, _ = await customer_service.ensure_customer_for_user(
                user_id,
                email=user["email"],
                name=user["full_name"],
                address=payload.billing_address,
                validate_tax_location=tax_enabled,
            )

        # Stripe writes (no DB transaction held; connection is
        # idle while we round-trip Stripe).
        await _sync_customer_billing_address(
            stripe_service, customer_id, user, payload, tax_enabled
        )

        # server-side replacement for the Stripe Radar CH-mismatch rule
        # runs before the chargeable Stripe call so a block never
        # creates a subscription.
        await ensure_ch_country_match(
            stripe_service,
            payment_method_id=payload.payment_method_id,
            billing_country=payload.billing_address.country,
        )

        stripe_subscription = await _create_stripe_subscription(
            stripe_service,
            customer_id=customer_id,
            payload=payload,
            user=user,
            tier=tier,
            price_id=price_id,
            discount_id=discount_id,
            quote=quote,
            tax_enabled=tax_enabled,
        )

        # local DB write inside a fresh transaction.
        # `expire_on_commit=True` (the session-factory default) marks
        # every attribute stale once the block exits; reading any
        # attribute on `subscription` after that triggers a sync-context
        # lazy-load that fails under asyncpg. So we capture the response
        # payload *before* the block exits and never touch the ORM
        # object again.
        deferred = PostCommitActions()
        response_details: SubscriptionDetails
        async with session.begin():
            subscription = await _stage_local_subscription(
                session=session,
                subscription_repo=subscription_repo,
                stripe_subscription=stripe_subscription,
                tier=tier,
                user_id=user_id,
                customer_id=customer_id,
                deferred=deferred,
            )
            await session.flush()  # ensure server-generated `id` is set
            response_details = SubscriptionDetails(
                id=subscription.id,
                status=subscription.status,
                current_period_start=subscription.current_period_start,
                current_period_end=subscription.current_period_end,
                type=subscription.subscription_type,
            )

            # Tier transition + (opt-in) profile address persistence run
            # *after* the commit — Keycloak is external, never inside the
            # DB transaction.
            _queue_post_commit_side_effects(
                deferred,
                user_id=user_id,
                payload=payload,
                stripe_status=str(stripe_subscription.status),
                subscription_repo=subscription_repo,
            )

        await deferred.run()

        return VliResponse.new(
            message="Subscription created successfully",
            data={"subscription": response_details.model_dump()},
        )

    except EntityAlreadyExists:
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
            message="This user already has an active subscription",
        )
    except (StripeCustomerCreationError, EntityNotCreated, SubscriptionMappingError):
        logger.exception("Stripe-side failure while creating subscription")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_CREATED,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Failed to create subscription with payment provider",
        )
    except ValueError as exc:
        # validation-style errors raised by quote/tier resolution.
        logger.warning(f"Subscription validation failed: {exc}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message=str(exc),
        )
    except CountryMismatchBlocked as exc:
        raise VliError(
            error_code=VliErrorCode.PAYMENT_ERROR,
            http_status_code=HTTPStatus.PAYMENT_REQUIRED,
            message=(
                "Payment could not be completed with the provided payment information. "
                "Please review your billing details and try again."
            ),
            details=str(exc),
        )
    except stripe._error.CardError as ex:
        raise VliError(
            error_code=VliErrorCode.PAYMENT_ERROR,
            http_status_code=HTTPStatus.PAYMENT_REQUIRED,
            message=ex.user_message,
        )
    except VliError:
        raise
    except Exception:
        logger.exception("Unexpected error creating subscription")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to create subscription",
        )


async def _check_no_active_paid_subscription(
    repo: SubscriptionRepository, user_id: UUID
) -> None:
    """Best-effort early reject before we make any Stripe call.

    The authoritative check happens inside the DB transaction with
    `FOR UPDATE` (see `_stage_local_subscription`) — this one only
    saves a Stripe round-trip in the common case.
    """
    existing = await repo.get_active_subscription_by_user_id(user_id, "paid")
    if existing is not None:
        raise EntityAlreadyExists


@dataclass(frozen=True, slots=True)
class _TierSnapshot:
    """Plain-value capture of a `SubscriptionTier`.

    The ORM object can't safely escape the Phase-1 transaction
    (`expire_on_commit=True` invalidates its attributes; touching them
    afterward triggers a sync lazy-load that fails under asyncpg).
    Snapshot what we need into primitives instead.
    """

    id: UUID
    kind: SubscriptionTierEnum


@dataclass(frozen=True, slots=True)
class _QuoteSnapshot:
    """Plain-value capture of a `BillingQuote` for the same reason."""

    id: UUID
    tax_status: TaxStatus
    subtotal: int
    tax_amount: int
    total: int
    stripe_tax_calculation_id: str | None


async def _resolve_tier_and_price(
    repo: SubscriptionRepository, payload: CreateSubscriptionRequest
) -> tuple[_TierSnapshot, str, str | None]:
    tier = await repo.get_subscription_tier_by_id(payload.tier_id)
    if tier is None:
        raise ValueError("Subscription plan not found")

    price_id = (
        tier.stripe_monthly_price_id
        if payload.interval == IntervalType.MONTH
        else tier.stripe_yearly_price_id
    )
    if not price_id:
        raise ValueError("Price ID not found")

    discount_id: str | None = None
    if settings.ENABLE_DISCOUNT:
        discount_id = (
            settings.DISCOUNT_MONTHLY_ID
            if payload.interval == IntervalType.MONTH
            else settings.DISCOUNT_YEARLY_ID
        )

    # Snapshot the ORM attributes *now* — the txn will commit shortly
    # and expire them.
    snapshot = _TierSnapshot(id=UUID(str(tier.id)), kind=tier.tier)
    return snapshot, price_id, discount_id


async def _resolve_quote(
    session: AsyncSession,
    payload: CreateSubscriptionRequest,
    user_id: UUID,
    tax_enabled: bool,
) -> _QuoteSnapshot | None:
    if payload.quote_id is None:
        if tax_enabled:
            raise ValueError("Billing quote is required for taxable subscriptions")
        return None

    quote = await BillingQuoteService(session).get_valid_quote(
        quote_id=payload.quote_id,
        user_id=user_id,
        flow=BillingFlow.SUBSCRIPTION,
        subscription_tier_id=payload.tier_id,
        interval=payload.interval.value,
    )
    if quote is None:
        raise ValueError("Billing quote expired or not found")

    # Snapshot before commit expires the ORM attributes.
    return _QuoteSnapshot(
        id=UUID(str(quote.id)),
        tax_status=quote.tax_status,
        subtotal=quote.subtotal,
        tax_amount=quote.tax_amount,
        total=quote.total,
        stripe_tax_calculation_id=quote.stripe_tax_calculation_id,
    )


async def _sync_customer_billing_address(
    stripe_service: StripeRepository,
    customer_id: str,
    user: dict[str, str],
    payload: CreateSubscriptionRequest,
    tax_enabled: bool,
) -> None:
    """Mirror the request's billing address onto the Stripe customer.

    Stripe Tax uses the customer's address to determine jurisdiction
    and to surface the correct address on receipts. This is independent
    of whether the user wants to persist the address back onto their
    Keycloak profile (handled later, post-commit, opt-in).
    """
    updated = await stripe_service.update_customer(
        customer_id=customer_id,
        email=user["email"],
        name=user["full_name"],
        address=payload.billing_address,
        validate_tax_location=tax_enabled,
    )
    if tax_enabled and updated is None:
        raise ValueError("Stripe could not validate billing address for tax")


async def _create_stripe_subscription(
    stripe_service: StripeRepository,
    *,
    customer_id: str,
    payload: CreateSubscriptionRequest,
    user: dict[str, str],
    tier: _TierSnapshot,
    price_id: str,
    discount_id: str | None,
    quote: _QuoteSnapshot | None,
    tax_enabled: bool,
) -> stripe.Subscription:
    metadata = _build_subscription_metadata(user=user, payload=payload, quote=quote)
    # Idempotency key: a retry of this exact subscribe action returns
    # the same Stripe subscription. The set of inputs (user, tier,
    # interval, payment method, quote) is what makes one request
    # distinct from another.
    idempotency_key = (
        f"sub:{user['user_id']}:{tier.id}:{payload.interval.value}"
        f":{payload.payment_method_id}:{payload.quote_id or 'no-quote'}"
    )
    stripe_subscription = await stripe_service.create_subscription(
        customer_id=customer_id,
        price_id=price_id,
        payment_method_id=payload.payment_method_id,
        metadata=metadata,
        discount_id=discount_id,
        automatic_tax_enabled=tax_enabled,
        idempotency_key=idempotency_key,
    )
    if stripe_subscription is None:
        raise EntityNotCreated
    return stripe_subscription


def _build_subscription_metadata(
    *,
    user: dict[str, str],
    payload: CreateSubscriptionRequest,
    quote: _QuoteSnapshot | None,
) -> dict[str, str]:
    """Stripe metadata sent on the Subscription. The webhook reads it
    back when reconciling the local row."""
    return {
        "user_id": str(user["user_id"]),
        "email": user["email"],
        "name": user["full_name"],
        "tax_country": payload.billing_address.country or "",
        "tax_behavior": settings.BILLING_TAX_BEHAVIOR,
        "tax_status": quote.tax_status.value if quote else "",
        "billing_quote_id": str(quote.id) if quote else "",
        "amount_subtotal": str(quote.subtotal) if quote else "",
        "amount_tax": str(quote.tax_amount) if quote else "",
        "amount_total": str(quote.total) if quote else "",
        "stripe_tax_calculation_id": (
            str(quote.stripe_tax_calculation_id or "") if quote else ""
        ),
    }


async def _stage_local_subscription(
    *,
    session: AsyncSession,
    subscription_repo: SubscriptionRepository,
    stripe_subscription: stripe.Subscription,
    tier: _TierSnapshot,
    user_id: UUID,
    customer_id: str,
    deferred: PostCommitActions,
) -> PaidSubscription:
    """Build the local PaidSubscription row from the Stripe response.

    Re-checks the active-subscription invariant under `FOR UPDATE` to
    close the race with concurrent requests. Uses the same mapping
    module the webhook handler uses, so the synchronous insert and
    the asynchronous webhook upsert can never produce different field
    values for the same Stripe subscription.
    """
    # Race close: this row-level lock blocks a concurrent
    # `create_subscription` for the same user until we commit, at
    # which point that other request sees the new row and rejects.
    locked_existing = await subscription_repo.get_active_paid_subscription_locked(
        user_id
    )
    if (
        locked_existing is not None
        and locked_existing.stripe_subscription_id != stripe_subscription.id
    ):
        # A different active subscription exists. We just minted a
        # Stripe subscription on this attempt; cancel it after we
        # commit (deferred so the cancel runs outside the DB txn).
        deferred.add(
            _wrap_cancel_subscription(stripe_subscription.id),
        )
        raise EntityAlreadyExists

    fields = map_stripe_subscription_to_db(
        stripe_subscription,
        tier_id=tier.id,
        tier_kind=tier.kind,
        user_id=user_id,
    )

    subscription = locked_existing or PaidSubscription()
    subscription.type = "paid"
    apply_subscription_fields(subscription, fields)
    subscription.customer_id = customer_id  # ensure non-null even if mapping skipped
    session.add(subscription)
    return subscription


def _queue_post_commit_side_effects(
    deferred: PostCommitActions,
    *,
    user_id: UUID,
    payload: CreateSubscriptionRequest,
    stripe_status: str,
    subscription_repo: SubscriptionRepository,
) -> None:
    """Tier transition + opt-in Keycloak address persistence.

    Both involve DB commits or external calls that don't belong
    inside the request transaction. They run after the local
    PaidSubscription row commits successfully.
    """
    if stripe_status != "active":
        deferred.add(_wrap_downgrade(subscription_repo, user_id))
    else:
        deferred.add(_wrap_deactivate_free(subscription_repo, user_id))

    if payload.sync_billing_address_to_profile:
        deferred.add(_wrap_save_billing_profile(user_id, payload.billing_address))


def _wrap_cancel_subscription(stripe_subscription_id: str) -> PostCommitRunner:
    async def _runner() -> None:
        try:
            await get_stripe_repository().cancel_subscription(
                stripe_subscription_id, cancel_immediately=True
            )
        except Exception:
            logger.exception(
                f"Post-commit cancel of Stripe subscription "
                f"{stripe_subscription_id} failed"
            )

    return _runner


def _wrap_downgrade(repo: SubscriptionRepository, user_id: UUID) -> PostCommitRunner:
    async def _runner() -> None:
        try:
            await repo.downgrade_to_free(user_id=user_id)
        except Exception:
            logger.exception(f"Post-commit downgrade_to_free for user {user_id} failed")

    return _runner


def _wrap_deactivate_free(
    repo: SubscriptionRepository, user_id: UUID
) -> PostCommitRunner:
    async def _runner() -> None:
        try:
            await repo.deactivate_free_subscription(user_id=user_id)
        except Exception:
            logger.exception(
                f"Post-commit deactivate_free_subscription for user {user_id} failed"
            )

    return _runner


def _wrap_save_billing_profile(
    user_id: UUID, address: BillingAddress
) -> PostCommitRunner:
    async def _runner() -> None:
        try:
            await save_billing_address_to_user_profile(user_id=user_id, address=address)
        except Exception:
            logger.exception(
                f"Post-commit Keycloak profile address save for user {user_id} failed"
            )

    return _runner
