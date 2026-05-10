"""Create a standalone (top-up) payment for a virtual lab.

The local DB row for this payment is created **by the webhook**
(`payment_intent.succeeded` → `_handle_standalone_payment_event`),
not by this usecase. Synchronously we only:

  1. Verify the user is authorized (admin of the lab).
  2. Resolve their billing quote.
  3. Ensure a Stripe customer exists for them (atomically — local
     row staged in the same transaction as the Stripe call result).
  4. Create the Stripe PaymentIntent with `confirm=True` so it
     charges immediately, using a deterministic idempotency key.
  5. Build a synchronous response from the typed Stripe objects.

If the call returns successfully, the user has been charged. The
webhook will arrive shortly and persist the local SubscriptionPayment
row with the canonical fields. If it doesn't arrive, Stripe retries
delivery for 3 days, and the webhook handler is find-or-create.

Address synced to the Stripe customer for tax jurisdiction; opt-in
persistence to the user's Keycloak profile happens after the local
DB transaction commits.
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
    EntityNotCreated,
    EntityNotFound,
    ForbiddenOperation,
)
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.billing import (
    BillingAddress,
    BillingFlow,
    TaxBehavior,
    TaxStatus,
)
from virtual_labs.domain.payment import CreateStandalonePaymentRequest
from virtual_labs.domain.subscription import StandalonePaymentResponse
from virtual_labs.infrastructure.db.models import PaymentStatus
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.infrastructure.stripe import helpers as stripe_helpers
from virtual_labs.infrastructure.stripe.types import PostCommitActions, PostCommitRunner
from virtual_labs.repositories.labs import get_virtual_lab_soft
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.services.billing import (
    BillingQuoteService,
    is_tax_enabled_for_country,
    save_billing_address_to_user_profile,
)
from virtual_labs.services.stripe_customer import (
    StripeCustomerCreationError,
    StripeCustomerService,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth, get_user_metadata


async def create_standalone_payment(
    payload: CreateStandalonePaymentRequest,
    session: AsyncSession,
    auth: tuple[AuthUser, str],
) -> Response:
    try:
        user_id = get_user_id_from_auth(auth)
        user = get_user_metadata(auth_user=auth[0])
        tax_enabled = is_tax_enabled_for_country(payload.billing_address.country)

        stripe_service = get_stripe_repository()
        customer_service = StripeCustomerService(
            session, stripe_repository=stripe_service
        )
        deferred = PostCommitActions()

        # gather + customer ensure inside one short transaction
        # we also capture every value we need from the loaded ORM
        # objects into local primitives *before* the block exits
        # `expire_on_commit=True` (default) marks attributes stale on
        # commit; reading them afterwards triggers a sync-context
        # lazy-load that fails under asyncpg with `MissingGreenlet`
        async with session.begin():
            await _validate_lab_admin(session, user_id, payload.virtual_lab_id)
            subscription_id = await _require_active_subscription_id(session, user_id)
            quote = await _require_valid_quote(session, payload, user_id)
            customer_id, _ = await customer_service.ensure_customer_for_user(
                user_id,
                email=user["email"],
                name=user["full_name"],
                address=payload.billing_address,
                validate_tax_location=tax_enabled,
            )
            # Opt-in Keycloak profile write deferred to post-commit so
            # the DB transaction stays tight and never holds the
            # connection across an external call.
            if payload.sync_billing_address_to_profile:
                deferred.add(
                    _wrap_save_billing_profile(user_id, payload.billing_address)
                )

        # The Stripe customer's billing address is part of the payment
        # surface (Stripe Tax + receipts)
        # Update outside the transaction, no DB connection held
        await _sync_customer_billing_address(
            stripe_service, customer_id, user, payload, tax_enabled
        )

        payment_intent = await _create_stripe_payment_intent(
            stripe_service,
            customer_id=customer_id,
            payload=payload,
            user_id=user_id,
            subscription_id=subscription_id,
            quote=quote,
        )

        await deferred.run()

        # synchronous response from the typed Stripe objects.
        return await _build_response(stripe_service, payment_intent, quote)

    except ForbiddenOperation:
        logger.warning(
            f"Forbidden standalone payment attempt by user (lab "
            f"{payload.virtual_lab_id})"
        )
        raise VliError(
            error_code=VliErrorCode.FORBIDDEN_OPERATION,
            http_status_code=HTTPStatus.FORBIDDEN,
            message="User is not an admin of the virtual lab",
        )
    except EntityNotFound as exc:
        # Internal-controlled message — safe to surface.
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=str(exc),
        )
    except (StripeCustomerCreationError, EntityNotCreated):
        logger.exception("Stripe-side failure while creating standalone payment")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_CREATED,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Failed to process payment with payment provider",
        )
    except ValueError as exc:
        logger.warning(f"Standalone payment validation failed: {exc}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message=str(exc),
        )
    except VliError:
        raise
    except stripe._error.CardError as ex:
        raise VliError(
            error_code=VliErrorCode.PAYMENT_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=ex.user_message,
        )
    except Exception:
        logger.exception("Unexpected error creating standalone payment")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to process payment",
        )


@dataclass(frozen=True, slots=True)
class _QuoteSnapshot:
    """Plain-value capture of a `BillingQuote`.

    the ORM object can't safely escape Phase 1's transaction
    `expire_on_commit=True` (default) invalidates its attributes; touching
    them afterward triggers a sync lazy-load that fails under asyncpg
    with `MissingGreenlet`.
    This snapshot what we need into primitives
    """

    id: UUID
    subtotal: int
    tax_amount: int
    total: int
    currency: str
    tax_country: str | None
    tax_behavior: TaxBehavior
    tax_status: TaxStatus
    stripe_tax_calculation_id: str | None


async def _validate_lab_admin(
    session: AsyncSession, user_id: UUID, virtual_lab_id: UUID
) -> None:
    virtual_lab = await get_virtual_lab_soft(db=session, lab_id=virtual_lab_id)
    if virtual_lab is None:
        raise EntityNotFound("Virtual lab not found")
    if not UserQueryRepository().is_user_in_group(
        user_id=user_id, group_id=str(virtual_lab.admin_group_id)
    ):
        raise ForbiddenOperation()


async def _require_active_subscription_id(session: AsyncSession, user_id: UUID) -> UUID:
    subscription = await SubscriptionRepository(
        db_session=session
    ).get_active_subscription_by_user_id(user_id=user_id)
    if subscription is None:
        raise EntityNotFound("Subscription not found")
    # Snapshot before commit — the ORM `id` attribute would expire.
    return UUID(str(subscription.id))


async def _require_valid_quote(
    session: AsyncSession,
    payload: CreateStandalonePaymentRequest,
    user_id: UUID,
) -> _QuoteSnapshot:
    quote = await BillingQuoteService(session).get_valid_quote(
        quote_id=payload.quote_id,
        user_id=user_id,
        flow=BillingFlow.STANDALONE,
        virtual_lab_id=payload.virtual_lab_id,
    )
    if quote is None:
        raise ValueError("Billing quote expired or not found")
    return _QuoteSnapshot(
        id=UUID(str(quote.id)),
        subtotal=quote.subtotal,
        tax_amount=quote.tax_amount,
        total=quote.total,
        currency=quote.currency,
        tax_country=quote.tax_country,
        tax_behavior=quote.tax_behavior,
        tax_status=quote.tax_status,
        stripe_tax_calculation_id=quote.stripe_tax_calculation_id,
    )


async def _sync_customer_billing_address(
    stripe_service: StripeRepository,
    customer_id: str,
    user: dict[str, str],
    payload: CreateStandalonePaymentRequest,
    tax_enabled: bool,
) -> None:
    """Mirror the request's billing address onto the Stripe customer.

    Stripe Tax uses the customer's address to determine jurisdiction
    and to surface the correct address on receipts.
    """
    await stripe_service.update_customer(
        customer_id=customer_id,
        email=user["email"],
        name=user["full_name"],
        address=payload.billing_address,
        validate_tax_location=tax_enabled,
    )


async def _create_stripe_payment_intent(
    stripe_service: StripeRepository,
    *,
    customer_id: str,
    payload: CreateStandalonePaymentRequest,
    user_id: UUID,
    subscription_id: UUID,
    quote: _QuoteSnapshot,
) -> stripe.PaymentIntent:
    metadata = {
        "user_id": str(user_id),
        "virtual_lab_id": str(payload.virtual_lab_id),
        "subscription_id": str(subscription_id),
        "standalone": "true",
        "billing_quote_id": str(quote.id),
        "amount_subtotal": str(quote.subtotal),
        "amount_tax": str(quote.tax_amount),
        "amount_total": str(quote.total),
        "tax_country": str(quote.tax_country or ""),
        "tax_behavior": quote.tax_behavior.value,
        "tax_status": quote.tax_status.value,
        "stripe_tax_calculation_id": str(quote.stripe_tax_calculation_id or ""),
    }
    # Idempotency key: a retry of this exact top-up returns the same
    # PaymentIntent rather than charging the user twice. Quote id is
    # the strongest single-use identifier we have here
    idempotency_key = f"pi:standalone:{quote.id}:{payload.payment_method_id}"
    return await stripe_service.create_payment_intent(
        amount=quote.total,
        currency=quote.currency,
        customer_id=customer_id,
        payment_method_id=payload.payment_method_id,
        tax_calculation_id=quote.stripe_tax_calculation_id,
        idempotency_key=idempotency_key,
        metadata=metadata,
    )


async def _build_response(
    stripe_service: StripeRepository,
    payment_intent: stripe.PaymentIntent,
    quote: _QuoteSnapshot,
) -> Response:
    """Assemble the synchronous response from typed Stripe objects."""
    receipt_url: str | None = None
    charge_id = payment_intent.latest_charge
    if isinstance(charge_id, str):
        charge = await stripe_service.get_charge(charge_id=charge_id)
        if charge is not None:
            receipt_url = charge.receipt_url

    payment_method = await stripe_service.get_payment_method(
        payment_method_id=str(payment_intent.payment_method)
    )
    card = stripe_helpers.get_card_details(
        # `get_card_details` operates on a PaymentIntent, wrap the
        # standalone PaymentMethod in a minimal stand-in so we reuse
        # the same extractor and produce identical defaults.
        _payment_method_envelope(payment_method)
    )

    response = StandalonePaymentResponse(
        amount=quote.total,
        amount_subtotal=quote.subtotal,
        amount_tax=quote.tax_amount,
        amount_total=quote.total,
        currency=quote.currency,
        tax_country=quote.tax_country,
        tax_behavior=quote.tax_behavior,
        tax_status=quote.tax_status,
        status=PaymentStatus(payment_intent.status),
        receipt_url=receipt_url,
        card_last4=card.last4 if card is not None else "0000",
        card_brand=card.brand if card is not None else "unknown",
    )
    return VliResponse.new(
        message="Payment processed successfully",
        data=response.model_dump(),
    )


def _payment_method_envelope(pm: stripe.PaymentMethod) -> stripe.PaymentIntent:
    """Wrap a PaymentMethod so `helpers.get_card_details` can read it.

    `get_card_details` was written for PaymentIntents (which have a
    `payment_method` field); we synthesize the minimal envelope it
    expects so both call sites use the same extractor.
    """
    envelope = stripe.PaymentIntent.construct_from({"payment_method": pm}, key=None)
    return envelope


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
