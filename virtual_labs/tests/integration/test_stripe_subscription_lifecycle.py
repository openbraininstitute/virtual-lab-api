"""Real-stack Stripe integration tests for the subscription lifecycle.

Drives the user story end-to-end against the live local stack
(Postgres, Keycloak, Redis, Stripe test mode + ``stripe listen``):

  1. user owns a virtual lab (free subscription auto-provisioned)
  2. user creates a paid subscription -> succeeds
  3. user creates a standalone top-up payment -> succeeds
  4. user cancels subscription -> succeeds

Plus the unhappy edge cases (declined card, duplicate active sub,
expired quote, missing quote with tax, non-admin top-up, declined
top-up, cancel without active sub, double-cancel).

The whole module is auto-skipped if the Stripe credentials, real
tier seeding, or stripe-cli forwarder are not present, so machines
without billing setup keep a green test run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Any, AsyncGenerator, Dict, Tuple
from uuid import UUID

import pytest
import pytest_asyncio
import stripe
from httpx import AsyncClient
from loguru import logger
from sqlalchemy import delete, select, update

from virtual_labs.infrastructure.db.models import (
    BillingQuote,
    FreeSubscription,
    PaidSubscription,
    PaymentStatus,
    StripeUser,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
    SubscriptionTier,
    SubscriptionTierEnum,
)
from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.tests.utils import (
    get_headers,
    session_context_factory,
    wait_until,
)

_REAL_SERVER_URL = "http://localhost:8000"


def _missing_stripe_env() -> str | None:
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_SECRET_KEY.startswith(
        "sk_test_"
    ):
        return "STRIPE_SECRET_KEY (test mode) not configured"
    if not settings.STRIPE_WEBHOOK_SECRET:
        return "STRIPE_WEBHOOK_SECRET not configured (stripe listen must be running)"
    return None


def _real_server_unreachable() -> bool:
    """The webhook flow requires Stripe -> stripe-cli -> a real HTTP
    server. The in-process ASGI client used elsewhere in this repo
    can't receive webhooks. Probe the dev server and skip otherwise.
    """
    import socket

    try:
        with socket.create_connection(("localhost", 8000), timeout=0.5):
            return False
    except OSError:
        return True


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration,
    pytest.mark.skipif(
        _missing_stripe_env() is not None,
        reason=_missing_stripe_env() or "",
    ),
    pytest.mark.skipif(
        _real_server_unreachable(),
        reason=(
            "real dev server on localhost:8000 not running -- start `make dev` "
            "in another terminal so Stripe webhooks can reach the app"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------


CH_ADDRESS: Dict[str, str] = {
    "name": "Ada Lovelace",
    "line1": "Rue de Lausanne 1",
    "city": "Geneva",
    "postal_code": "1201",
    "country": "CH",
}

# Non-CH billing address used to exercise the path that does NOT touch
# the CH country-mismatch guard (CH-flagged paths require card_country
# == billing_country == CH).
US_ADDRESS: Dict[str, str] = {
    "name": "Ada Lovelace",
    "line1": "1 Market St",
    "city": "San Francisco",
    "state": "CA",
    "postal_code": "94105",
    "country": "US",
}

WEBHOOK_TIMEOUT_S = 45  # plenty of slack for stripe listen forwarding.


async def _get_pro_tier_id() -> UUID:
    async with session_context_factory() as session:
        tier = (
            await session.execute(
                select(SubscriptionTier).where(
                    SubscriptionTier.tier == SubscriptionTierEnum.PRO
                )
            )
        ).scalar_one_or_none()
    if tier is None or not tier.stripe_monthly_price_id:
        pytest.skip(
            "PRO subscription_tier with a real Stripe monthly price id is "
            "not seeded; run `poetry run populate-tiers` (no --test)."
        )
    if str(tier.stripe_monthly_price_id).endswith("Example123"):
        pytest.skip(
            "PRO tier is seeded with placeholder Stripe price ids; "
            "run `poetry run populate-tiers` against the real Stripe key."
        )
    return UUID(str(tier.id))


async def _drop_user_subscriptions(user_id: UUID) -> None:
    """Tear down user-scoped subscription/payment rows left behind by
    previous tests so the new test starts from a clean state.

    `cleanup_resources` drops rows by `virtual_lab_id`, but paid
    subscriptions (and recurring payments) carry no `virtual_lab_id`,
    so they survive across tests for the same user. We delete them
    explicitly here.
    """
    async with session_context_factory() as session:
        sub_ids = (
            (
                await session.execute(
                    select(Subscription.id).where(Subscription.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        if sub_ids:
            await session.execute(
                delete(SubscriptionPayment).where(
                    SubscriptionPayment.subscription_id.in_(sub_ids)
                )
            )
            await session.execute(
                delete(FreeSubscription).where(FreeSubscription.id.in_(sub_ids))
            )
            await session.execute(
                delete(PaidSubscription).where(PaidSubscription.id.in_(sub_ids))
            )
            await session.execute(
                delete(Subscription).where(Subscription.id.in_(sub_ids))
            )
        await session.commit()


async def _reset_stripe_state(user_id: UUID) -> None:
    """Pin a fresh Stripe customer to the user before the test runs.

    The production `ensure_customer_for_user` uses a deterministic
    Stripe idempotency key (``customer:user:{user_id}``); once Stripe
    has cached a response for that key, *every* later call replays the
    same customer id -- even after the customer was deleted. To break
    that loop in tests, we mint a brand-new customer ourselves (no
    idempotency key) and upsert the local `stripe_user` row to point
    at it. Production code then finds an existing local row and reuses
    our fresh customer instead of going through the cached create.

    We deliberately don't delete the previous Stripe customer here --
    deleting it would only re-arm the idempotency replay. Test-mode
    orphans are harmless.
    """
    fresh_customer = await stripe_client.customers.create_async(
        params={"description": f"vli-integration-test:{user_id}"}
    )
    async with session_context_factory() as session:
        existing = (
            await session.execute(
                select(StripeUser).where(StripeUser.user_id == user_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                StripeUser(
                    user_id=user_id,
                    stripe_customer_id=fresh_customer.id,
                )
            )
        else:
            existing.stripe_customer_id = fresh_customer.id
        await session.commit()


async def _create_payment_method(card_pm: str = "pm_card_visa") -> str:
    """Return a fresh, unattached Stripe PaymentMethod id for the requested
    test card.

    Stripe's ``pm_card_*`` test ids are "magic" shared PaymentMethods that
    can't be reattached arbitrarily across customers, so we always mint a
    fresh PaymentMethod via ``payment_methods.create_async`` using the
    matching test token. The local subscription/standalone-payment code
    paths attach this PM to the user's customer themselves.
    """
    # `tok_ch` is Stripe's Swiss-issued test token; the standalone aliases
    # below are US-issued.
    token_map = {
        "pm_card_visa": "tok_visa",
        "pm_card_chargeDeclined": "tok_chargeDeclined",
        "pm_card_ch": "tok_ch",
    }
    token = token_map.get(card_pm)
    if token is None:
        raise ValueError(f"Unsupported test PM alias: {card_pm}")
    pm = await stripe_client.payment_methods.create_async(
        params={"type": "card", "card": {"token": token}}
    )
    return str(pm.id)


async def _create_billing_quote(
    client: AsyncClient,
    *,
    user: str,
    flow: str,
    virtual_lab_id: UUID | None = None,
    credits: int | None = None,
    tier_id: UUID | None = None,
    interval: str | None = None,
    billing_address: Dict[str, str] | None = None,
    currency: str = "chf",
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "flow": flow,
        "currency": currency,
        "billing_address": billing_address or CH_ADDRESS,
    }
    if virtual_lab_id is not None:
        body["virtual_lab_id"] = str(virtual_lab_id)
    if credits is not None:
        body["credits"] = credits
    if tier_id is not None:
        body["tier_id"] = str(tier_id)
    if interval is not None:
        body["interval"] = interval

    response = await client.post(
        "/billing/quotes", json=body, headers=get_headers(user)
    )
    assert response.status_code == HTTPStatus.OK, response.text
    data: Dict[str, Any] = response.json()["data"]
    return data


async def _paid_sub_for_user(user_id: UUID) -> PaidSubscription | None:
    """Return the most-recent paid_subscription for a user, or None.

    Older test runs may have left rows behind (paid subs are
    user-scoped, not lab-scoped, so `cleanup_resources` doesn't drop
    them). We pick the newest so we always see the just-created sub.
    """
    async with session_context_factory() as session:
        return (
            await session.execute(
                select(PaidSubscription)
                .where(PaidSubscription.user_id == user_id)
                .order_by(PaidSubscription.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()


async def _wait_paid_active(user_id: UUID) -> bool:
    async def predicate() -> bool:
        sub = await _paid_sub_for_user(user_id)
        return sub is not None and sub.status == SubscriptionStatus.ACTIVE

    return await wait_until(predicate, timeout=WEBHOOK_TIMEOUT_S)


async def _wait_recurring_payment_recorded(subscription_id: UUID) -> bool:
    async def predicate() -> bool:
        async with session_context_factory() as session:
            row = (
                await session.execute(
                    select(SubscriptionPayment).where(
                        SubscriptionPayment.subscription_id == subscription_id,
                        SubscriptionPayment.standalone.is_(False),
                        SubscriptionPayment.status == PaymentStatus.SUCCEEDED,
                    )
                )
            ).first()
            return row is not None

    return await wait_until(predicate, timeout=WEBHOOK_TIMEOUT_S)


async def _wait_standalone_payment_recorded(virtual_lab_id: UUID) -> bool:
    async def predicate() -> bool:
        async with session_context_factory() as session:
            row = (
                await session.execute(
                    select(SubscriptionPayment).where(
                        SubscriptionPayment.virtual_lab_id == virtual_lab_id,
                        SubscriptionPayment.standalone.is_(True),
                        SubscriptionPayment.status == PaymentStatus.SUCCEEDED,
                    )
                )
            ).first()
            return row is not None

    return await wait_until(predicate, timeout=WEBHOOK_TIMEOUT_S)


async def _wait_cancel_at_period_end(stripe_subscription_id: str) -> bool:
    async def predicate() -> bool:
        sub = await stripe_client.subscriptions.retrieve_async(stripe_subscription_id)
        return bool(sub.cancel_at_period_end)

    return await wait_until(predicate, timeout=WEBHOOK_TIMEOUT_S)


@pytest_asyncio.fixture
async def real_http_client() -> AsyncGenerator[AsyncClient, None]:
    """An httpx client that hits the real dev server on localhost:8000
    rather than the in-process ASGI app, so Stripe webhooks delivered
    by `stripe listen` actually reach the same process the test is
    asserting against."""
    from virtual_labs.tests.utils import get_headers

    async with AsyncClient(
        base_url=_REAL_SERVER_URL,
        headers=get_headers(),
        timeout=30.0,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def reset_stripe_for_test(
    test_user_ids: Dict[str, str],
) -> AsyncGenerator[None, None]:
    """Drop any stripe_user rows for the test users so each test starts
    from a clean Stripe-side state. Stale Stripe customer ids carried
    over from prior runs would otherwise 500 the create-subscription
    flow ("No such customer")."""
    for username in ("test", "test-1"):
        if username in test_user_ids:
            user_id = UUID(test_user_ids[username])
            await _drop_user_subscriptions(user_id)
            await _reset_stripe_state(user_id)
    yield


@pytest_asyncio.fixture
async def stripe_cleanup() -> AsyncGenerator[set[str], None]:
    """Cancel any live Stripe subscriptions created by the test.

    DB rows are cleaned up by `created_lab` -> `cleanup_resources`.
    We deliberately don't delete Stripe customers -- doing so would
    re-arm the idempotency-key replay that pinned a dead customer id
    in `_reset_stripe_state`'s docstring.
    """
    subscription_ids: set[str] = set()
    try:
        yield subscription_ids
    finally:
        for sub_id in subscription_ids:
            try:
                await stripe_client.subscriptions.cancel_async(
                    sub_id,
                    {"invoice_now": False, "prorate": False},
                )
            except stripe.InvalidRequestError:
                pass
            except Exception as e:
                logger.warning(f"Stripe subscription cleanup for {sub_id} failed: {e}")


async def _track_subscription_for_cleanup(
    user_id: UUID, subscription_ids: set[str]
) -> None:
    sub = await _paid_sub_for_user(user_id)
    if sub is not None and sub.stripe_subscription_id:
        subscription_ids.add(str(sub.stripe_subscription_id))


# ---------------------------------------------------------------------------
# Happy-path: full lifecycle
# ---------------------------------------------------------------------------


async def test_subscription_full_lifecycle_happy_path(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
    stripe_cleanup: set[str],
) -> None:
    lab_id_str, _, owner_id_str = created_lab
    lab_id = UUID(lab_id_str)
    owner_id = UUID(owner_id_str)
    headers = get_headers("test")

    # 1. Free subscription was auto-provisioned with the lab.
    active = await real_http_client.get("/subscriptions/active", headers=headers)
    assert active.status_code == HTTPStatus.OK, active.text
    assert active.json()["data"]["subscription"]["type"] == "free"

    # 2. Set up: tier, payment method, quote.
    #    Use a Swiss-issued card (`pm_card_ch`) so it matches the CH billing
    #    address; mismatched (card_country, billing_country) pairs are
    #    blocked by `ensure_ch_country_match`.
    tier_id = await _get_pro_tier_id()
    payment_method_id = await _create_payment_method("pm_card_ch")
    sub_quote = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="subscription",
        virtual_lab_id=lab_id,
        tier_id=tier_id,
        interval="month",
    )

    # 3. Create the paid subscription.
    create_resp = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": payment_method_id,
            "quote_id": sub_quote["quote_id"],
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    await _track_subscription_for_cleanup(owner_id, stripe_cleanup)
    assert create_resp.status_code == HTTPStatus.OK, create_resp.text
    new_subscription_id = UUID(create_resp.json()["data"]["subscription"]["id"])

    # 4. Wait for create + invoice.payment_succeeded webhooks to land.
    assert await _wait_paid_active(owner_id), (
        "paid_subscription did not become ACTIVE within timeout"
    )
    assert await _wait_recurring_payment_recorded(new_subscription_id), (
        "no recurring subscription_payment row recorded for the new subscription"
    )

    # 5. Standalone top-up.
    topup_quote = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="standalone",
        virtual_lab_id=lab_id,
        credits=200,
    )
    topup_pm = await _create_payment_method("pm_card_ch")
    topup_resp = await real_http_client.post(
        "/payments/standalone",
        json={
            "quote_id": topup_quote["quote_id"],
            "virtual_lab_id": str(lab_id),
            "payment_method_id": topup_pm,
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    assert topup_resp.status_code == HTTPStatus.OK, topup_resp.text
    assert topup_resp.json()["data"]["status"] == PaymentStatus.SUCCEEDED.value

    assert await _wait_standalone_payment_recorded(lab_id), (
        "standalone subscription_payment row was not recorded"
    )

    # 6. Cancel.
    cancel_resp = await real_http_client.request(
        "DELETE",
        "/subscriptions",
        json={"reason": "integration test teardown"},
        headers=headers,
    )
    assert cancel_resp.status_code == HTTPStatus.OK, cancel_resp.text

    sub = await _paid_sub_for_user(owner_id)
    assert sub is not None and sub.cancel_at_period_end is True
    assert sub.stripe_subscription_id is not None
    assert await _wait_cancel_at_period_end(str(sub.stripe_subscription_id))


# ---------------------------------------------------------------------------
# Unhappy paths
# ---------------------------------------------------------------------------


async def test_create_subscription_rejects_declined_card(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
    stripe_cleanup: set[str],
) -> None:
    _, _, owner_id_str = created_lab
    owner_id = UUID(owner_id_str)
    headers = get_headers("test")

    # `tok_chargeDeclined` is a US-issued declined-card token. Pair it with
    # a US billing address so the CH country-mismatch guard does not
    # short-circuit the decline path we're trying to exercise.
    lab_id = UUID(created_lab[0])
    tier_id = await _get_pro_tier_id()
    declined_pm = await _create_payment_method("pm_card_chargeDeclined")
    sub_quote = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="subscription",
        virtual_lab_id=lab_id,
        tier_id=tier_id,
        interval="month",
        billing_address=US_ADDRESS,
        currency="usd",
    )

    response = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": declined_pm,
            "quote_id": sub_quote["quote_id"],
            "billing_address": US_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    await _track_subscription_for_cleanup(owner_id, stripe_cleanup)
    # Stripe raises `CardError` on charge with `pm_card_chargeDeclined`;
    # the production handler maps that to 402 PAYMENT_REQUIRED with the
    # user-facing decline message surfaced as `message`.
    assert response.status_code == HTTPStatus.PAYMENT_REQUIRED, response.text
    body = response.json()
    assert body.get("error_code") == "PAYMENT_ERROR"
    assert "declined" in (body.get("message") or "").lower()


async def test_create_subscription_rejects_duplicate_active_subscription(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
    stripe_cleanup: set[str],
) -> None:
    _, _, owner_id_str = created_lab
    owner_id = UUID(owner_id_str)
    headers = get_headers("test")

    lab_id = UUID(created_lab[0])
    tier_id = await _get_pro_tier_id()
    pm1 = await _create_payment_method("pm_card_ch")
    quote1 = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="subscription",
        virtual_lab_id=lab_id,
        tier_id=tier_id,
        interval="month",
    )
    first = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": pm1,
            "quote_id": quote1["quote_id"],
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    await _track_subscription_for_cleanup(owner_id, stripe_cleanup)
    assert first.status_code == HTTPStatus.OK, first.text
    assert await _wait_paid_active(owner_id)

    pm2 = await _create_payment_method("pm_card_ch")
    quote2 = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="subscription",
        virtual_lab_id=lab_id,
        tier_id=tier_id,
        interval="month",
    )
    second = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": pm2,
            "quote_id": quote2["quote_id"],
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    assert second.status_code == HTTPStatus.CONFLICT, second.text


async def test_create_subscription_rejects_expired_quote(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
) -> None:
    headers = get_headers("test")
    lab_id = UUID(created_lab[0])
    tier_id = await _get_pro_tier_id()
    payment_method_id = await _create_payment_method("pm_card_visa")
    quote = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="subscription",
        virtual_lab_id=lab_id,
        tier_id=tier_id,
        interval="month",
    )

    async with session_context_factory() as session:
        await session.execute(
            update(BillingQuote)
            .where(BillingQuote.id == UUID(quote["quote_id"]))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await session.commit()

    response = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": payment_method_id,
            "quote_id": quote["quote_id"],
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST, response.text


async def test_create_subscription_rejects_missing_quote_when_tax_enabled(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
) -> None:
    headers = get_headers("test")
    tier_id = await _get_pro_tier_id()
    payment_method_id = await _create_payment_method("pm_card_visa")

    response = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": payment_method_id,
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST, response.text


async def test_standalone_payment_rejects_non_admin(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
    stripe_cleanup: set[str],
) -> None:
    lab_id_str, _, owner_id_str = created_lab
    lab_id = UUID(lab_id_str)
    owner_id = UUID(owner_id_str)
    owner_headers = get_headers("test")
    intruder_headers = get_headers("test-1")

    # An active subscription is required by `_require_active_subscription_id`,
    # so spin one up for the owner first. CH card + CH billing satisfies the
    # country-match guard.
    tier_id = await _get_pro_tier_id()
    pm = await _create_payment_method("pm_card_ch")
    sub_quote = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="subscription",
        virtual_lab_id=lab_id,
        tier_id=tier_id,
        interval="month",
    )
    create = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": pm,
            "quote_id": sub_quote["quote_id"],
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=owner_headers,
    )
    await _track_subscription_for_cleanup(owner_id, stripe_cleanup)
    assert create.status_code == HTTPStatus.OK
    assert await _wait_paid_active(owner_id)

    # The intruder needs *some* subscription to even reach the admin
    # check, so give them a free sub via lab creation in real life --
    # here we instead exercise the admin guard, which fires before
    # subscription resolution. Use the owner's quote id to keep the
    # surface minimal; the call should fail at the admin gate.
    topup_quote = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="standalone",
        virtual_lab_id=lab_id,
        credits=200,
    )
    intruder_pm = await _create_payment_method("pm_card_ch")
    response = await real_http_client.post(
        "/payments/standalone",
        json={
            "quote_id": topup_quote["quote_id"],
            "virtual_lab_id": str(lab_id),
            "payment_method_id": intruder_pm,
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=intruder_headers,
    )
    assert response.status_code == HTTPStatus.FORBIDDEN, response.text


async def test_cancel_subscription_without_active_returns_404(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
) -> None:
    headers = get_headers("test")
    response = await real_http_client.request(
        "DELETE",
        "/subscriptions",
        json={"reason": "no active subscription"},
        headers=headers,
    )
    assert response.status_code == HTTPStatus.NOT_FOUND, response.text


async def test_cancel_subscription_idempotent_already_canceled(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
    stripe_cleanup: set[str],
) -> None:
    _, _, owner_id_str = created_lab
    owner_id = UUID(owner_id_str)
    headers = get_headers("test")

    lab_id = UUID(created_lab[0])
    tier_id = await _get_pro_tier_id()
    pm = await _create_payment_method("pm_card_ch")
    quote = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="subscription",
        virtual_lab_id=lab_id,
        tier_id=tier_id,
        interval="month",
    )
    create = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": pm,
            "quote_id": quote["quote_id"],
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    await _track_subscription_for_cleanup(owner_id, stripe_cleanup)
    assert create.status_code == HTTPStatus.OK
    assert await _wait_paid_active(owner_id)

    first_cancel = await real_http_client.request(
        "DELETE",
        "/subscriptions",
        json={"reason": "first cancel"},
        headers=headers,
    )
    assert first_cancel.status_code == HTTPStatus.OK, first_cancel.text

    second_cancel = await real_http_client.request(
        "DELETE",
        "/subscriptions",
        json={"reason": "second cancel"},
        headers=headers,
    )
    assert second_cancel.status_code == HTTPStatus.BAD_REQUEST, second_cancel.text


# ---------------------------------------------------------------------------
# CH country-mismatch guard (server-side replacement for the Stripe
# Radar rule). Mirrors the policy: block when CH appears on exactly one
# of (card issuer country, billing country).
# ---------------------------------------------------------------------------


async def test_create_subscription_non_ch_billing_matching_card_succeeds(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
    stripe_cleanup: set[str],
) -> None:
    """Non-CH billing + non-CH card: guard is a no-op, subscription
    flow runs the same as the CH happy path."""
    _, _, owner_id_str = created_lab
    owner_id = UUID(owner_id_str)
    headers = get_headers("test")

    tier_id = await _get_pro_tier_id()
    payment_method_id = await _create_payment_method("pm_card_visa")
    # Tax is only enabled for CH by default; a US-billed subscription is
    # legal without a quote, so we skip the quote here on purpose.
    response = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": payment_method_id,
            "billing_address": US_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    await _track_subscription_for_cleanup(owner_id, stripe_cleanup)
    assert response.status_code == HTTPStatus.OK, response.text
    assert await _wait_paid_active(owner_id)


async def test_create_subscription_blocks_ch_billing_with_non_ch_card(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
    stripe_cleanup: set[str],
) -> None:
    """CH billing + US-issued card: guard rejects before any charge."""
    _, _, owner_id_str = created_lab
    owner_id = UUID(owner_id_str)
    headers = get_headers("test")

    lab_id = UUID(created_lab[0])
    tier_id = await _get_pro_tier_id()
    payment_method_id = await _create_payment_method("pm_card_visa")
    sub_quote = await _create_billing_quote(
        real_http_client,
        user="test",
        flow="subscription",
        virtual_lab_id=lab_id,
        tier_id=tier_id,
        interval="month",
    )
    response = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": payment_method_id,
            "quote_id": sub_quote["quote_id"],
            "billing_address": CH_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    await _track_subscription_for_cleanup(owner_id, stripe_cleanup)
    # 402 with the CH-mismatch detail is sufficient evidence the guard
    # fired before any Stripe charge. We deliberately do not assert
    # "no paid subscription row" here because a prior test's
    # `customer.subscription.created` webhook can race the next test
    # setup and recreate the row asynchronously.
    assert response.status_code == HTTPStatus.PAYMENT_REQUIRED, response.text
    body = response.json()
    assert body.get("error_code") == "PAYMENT_ERROR"
    assert "CH country mismatch" in (body.get("details") or "")


async def test_create_subscription_blocks_non_ch_billing_with_ch_card(
    real_http_client: AsyncClient,
    reset_stripe_for_test: None,
    created_lab: Tuple[str, Dict[str, Any], str],
    stripe_cleanup: set[str],
) -> None:
    """Non-CH billing + CH-issued card: guard rejects in the symmetric
    direction. Quote is optional because tax is not enabled for US."""
    _, _, owner_id_str = created_lab
    owner_id = UUID(owner_id_str)
    headers = get_headers("test")

    tier_id = await _get_pro_tier_id()
    payment_method_id = await _create_payment_method("pm_card_ch")
    response = await real_http_client.post(
        "/subscriptions",
        json={
            "tier_id": str(tier_id),
            "interval": "month",
            "payment_method_id": payment_method_id,
            "billing_address": US_ADDRESS,
            "sync_billing_address_to_profile": False,
        },
        headers=headers,
    )
    await _track_subscription_for_cleanup(owner_id, stripe_cleanup)
    # See note on the sibling test above: webhook timing makes the
    # "no paid subscription row" check flaky, the 402 is the load-
    # bearing assertion here.
    assert response.status_code == HTTPStatus.PAYMENT_REQUIRED, response.text
