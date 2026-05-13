"""Dispatch and post-commit-action tests for `StripeWebhook`.

These exercise the routing layer and the atomicity primitive
(`PostCommitActions`) without touching a real DB. The full
DB-rollback semantics are covered by the existing integration
suite that hits the FastAPI route end-to-end.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
import stripe
from stripe import convert_to_stripe_object

from virtual_labs.infrastructure.stripe.webhook import StripeWebhook
from virtual_labs.infrastructure.stripe.types import PostCommitActions


def _make_webhook(redis: AsyncMock | MagicMock | None = None) -> StripeWebhook:
    return StripeWebhook(
        stripe_repository=MagicMock(),
        subscription_repository=MagicMock(),
        stripe_user_repository=MagicMock(),
        credit_converter=MagicMock(),
        redis=redis or AsyncMock(),
    )


def _build_event(event_type: str, payload_object: dict[str, Any]) -> stripe.Event:
    payload = {
        "id": "evt_test_1",
        "type": event_type,
        "data": {"object": payload_object},
    }
    return cast(stripe.Event, convert_to_stripe_object(payload))


# Dispatch routing
@pytest.mark.parametrize(
    "event_type",
    sorted(StripeWebhook.subscription_update_events),
)
@pytest.mark.asyncio
async def test_subscription_events_route_to_subscription_handler(
    event_type: str,
) -> None:
    redis = AsyncMock()
    redis.set.return_value = True  # idempotency claim succeeds
    webhook = _make_webhook(redis=redis)
    event = _build_event(
        event_type, {"id": "sub_x", "object": "subscription", "metadata": {}}
    )

    sub_handler = AsyncMock(return_value={"status": "success"})
    invoice_handler = AsyncMock()
    standalone_handler = AsyncMock()
    webhook._handlers = {
        e: sub_handler for e in StripeWebhook.subscription_update_events
    }
    webhook._handlers.update(
        {e: invoice_handler for e in StripeWebhook.payment_update_events}
    )
    setattr(webhook, "_handle_standalone_payment_event", standalone_handler)

    result = await webhook.handle_webhook_event(event, MagicMock())

    sub_handler.assert_awaited_once()
    invoice_handler.assert_not_called()
    standalone_handler.assert_not_called()
    assert result == {"status": "success"}


@pytest.mark.parametrize(
    "event_type",
    sorted(StripeWebhook.payment_update_events),
)
@pytest.mark.asyncio
async def test_invoice_events_route_to_invoice_handler(event_type: str) -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    webhook = _make_webhook(redis=redis)
    event = _build_event(
        event_type, {"id": "in_x", "object": "invoice", "metadata": {}}
    )

    sub_handler = AsyncMock()
    invoice_handler = AsyncMock(return_value={"status": "success"})
    webhook._handlers = {
        e: sub_handler for e in StripeWebhook.subscription_update_events
    }
    webhook._handlers.update(
        {e: invoice_handler for e in StripeWebhook.payment_update_events}
    )

    result = await webhook.handle_webhook_event(event, MagicMock())

    invoice_handler.assert_awaited_once()
    sub_handler.assert_not_called()
    assert result == {"status": "success"}


@pytest.mark.parametrize(
    "event_type",
    sorted(StripeWebhook.standalone_payment_events),
)
@pytest.mark.asyncio
async def test_standalone_events_with_metadata_route_to_standalone_handler(
    event_type: str,
) -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    webhook = _make_webhook(redis=redis)
    event = _build_event(
        event_type,
        {
            "id": "pi_x",
            "object": "payment_intent",
            "metadata": {"standalone": "true"},
        },
    )

    standalone_handler = AsyncMock(return_value={"status": "success"})
    setattr(webhook, "_handle_standalone_payment_event", standalone_handler)

    result = await webhook.handle_webhook_event(event, MagicMock())

    standalone_handler.assert_awaited_once()
    assert result == {"status": "success"}


@pytest.mark.parametrize(
    "event_type",
    sorted(StripeWebhook.standalone_payment_events),
)
@pytest.mark.asyncio
async def test_standalone_event_types_without_metadata_are_ignored(
    event_type: str,
) -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    webhook = _make_webhook(redis=redis)
    # No `standalone` metadata: not a topup, falls through to ignored
    event = _build_event(
        event_type, {"id": "pi_x", "object": "payment_intent", "metadata": {}}
    )

    standalone_handler = AsyncMock()
    setattr(webhook, "_handle_standalone_payment_event", standalone_handler)
    # No registered handlers for these event types
    webhook._handlers = {}

    result = await webhook.handle_webhook_event(event, MagicMock())

    standalone_handler.assert_not_called()
    assert result["status"] == "ignored"
    assert result["event_type"] == event_type


@pytest.mark.asyncio
async def test_unknown_event_type_returns_ignored() -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    webhook = _make_webhook(redis=redis)
    event = _build_event(
        "charge.updated", {"id": "ch_x", "object": "charge", "metadata": {}}
    )

    result = await webhook.handle_webhook_event(event, MagicMock())

    assert result == {"status": "ignored", "event_type": "charge.updated"}


@pytest.mark.asyncio
async def test_duplicate_event_returns_duplicate() -> None:
    redis = AsyncMock()
    redis.set.return_value = False  # SET-NX fails => duplicate
    webhook = _make_webhook(redis=redis)
    event = _build_event(
        "customer.subscription.updated",
        {"id": "sub_x", "object": "subscription", "metadata": {}},
    )

    handler = AsyncMock()
    webhook._handlers = {e: handler for e in StripeWebhook.subscription_update_events}

    result = await webhook.handle_webhook_event(event, MagicMock())

    handler.assert_not_called()
    assert result["status"] == "duplicate"
    assert result["event_id"] == "evt_test_1"


@pytest.mark.asyncio
async def test_handler_exception_returns_error_status() -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    webhook = _make_webhook(redis=redis)
    event = _build_event(
        "customer.subscription.updated",
        {"id": "sub_x", "object": "subscription", "metadata": {}},
    )

    failing = AsyncMock(side_effect=RuntimeError("boom"))
    webhook._handlers = {e: failing for e in StripeWebhook.subscription_update_events}

    result = await webhook.handle_webhook_event(event, MagicMock())

    assert result["status"] == "error"
    assert "boom" in result["message"]


# Subscription handler split: deleted vs. upsert
@pytest.mark.parametrize(
    "event_type",
    sorted(StripeWebhook.subscription_upsert_events),
)
@pytest.mark.asyncio
async def test_upsert_subscription_events_route_to_upsert_handler(
    event_type: str,
) -> None:
    """created / updated / pending_* must hit the upsert handler, never deleted."""
    redis = AsyncMock()
    redis.set.return_value = True
    webhook = _make_webhook(redis=redis)
    event = _build_event(
        event_type, {"id": "sub_x", "object": "subscription", "metadata": {}}
    )

    upsert = AsyncMock(return_value={"status": "success"})
    deleted = AsyncMock()
    webhook._handlers = {
        **{e: upsert for e in StripeWebhook.subscription_upsert_events},
        **{e: deleted for e in StripeWebhook.subscription_deleted_events},
    }

    result = await webhook.handle_webhook_event(event, MagicMock())

    upsert.assert_awaited_once()
    deleted.assert_not_called()
    assert result == {"status": "success"}


@pytest.mark.asyncio
async def test_deleted_subscription_event_routes_to_deleted_handler() -> None:
    """customer.subscription.deleted must hit the deleted handler, never upsert."""
    redis = AsyncMock()
    redis.set.return_value = True
    webhook = _make_webhook(redis=redis)
    event = _build_event(
        "customer.subscription.deleted",
        {"id": "sub_x", "object": "subscription", "metadata": {}},
    )

    upsert = AsyncMock()
    deleted = AsyncMock(return_value={"status": "success"})
    webhook._handlers = {
        **{e: upsert for e in StripeWebhook.subscription_upsert_events},
        **{e: deleted for e in StripeWebhook.subscription_deleted_events},
    }

    result = await webhook.handle_webhook_event(event, MagicMock())

    deleted.assert_awaited_once()
    upsert.assert_not_called()
    assert result == {"status": "success"}


def test_event_sets_partition_subscription_events() -> None:
    """upsert ∪ deleted == all subscription events; intersection is empty."""
    upsert = StripeWebhook.subscription_upsert_events
    deleted = StripeWebhook.subscription_deleted_events
    union = StripeWebhook.subscription_update_events
    assert upsert | deleted == union
    assert upsert & deleted == frozenset()


# PostCommitActions
@pytest.mark.asyncio
async def test_post_commit_actions_run_in_order() -> None:
    actions = PostCommitActions()
    calls: list[str] = []

    async def first() -> None:
        calls.append("first")

    async def second() -> None:
        calls.append("second")

    actions.add(first)
    actions.add(second)
    await actions.run()
    assert calls == ["first", "second"]


@pytest.mark.asyncio
async def test_post_commit_action_failure_does_not_block_subsequent_actions() -> None:
    """A failing post-commit action should be logged and the next one still runs.

    DB has already committed at this point — we must not break the world if
    Keycloak/accounting has a transient outage.
    """
    actions = PostCommitActions()
    calls: list[str] = []

    async def fails() -> None:
        calls.append("attempted_first")
        raise RuntimeError("kc down")

    async def runs() -> None:
        calls.append("ran_second")

    actions.add(fails)
    actions.add(runs)
    await actions.run()
    assert calls == ["attempted_first", "ran_second"]


@pytest.mark.asyncio
async def test_empty_post_commit_actions_is_a_noop() -> None:
    actions = PostCommitActions()
    await actions.run()  # must not raise


# ---------------------------------------------------------------------------
# Idempotency claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_idempotency_returns_true_for_missing_event_id() -> None:
    redis = AsyncMock()
    webhook = _make_webhook(redis=redis)
    assert await webhook._claim_idempotency(None) is True
    assert await webhook._claim_idempotency("") is True
    redis.set.assert_not_called()


@pytest.mark.asyncio
async def test_claim_idempotency_uses_setnx_with_ttl() -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    webhook = _make_webhook(redis=redis)

    result = await webhook._claim_idempotency("evt_abc")

    assert result is True
    redis.set.assert_awaited_once()
    args, kwargs = redis.set.call_args
    assert args[0] == "stripe:webhook:processed:evt_abc"
    assert args[1] == "1"
    assert kwargs.get("nx") is True
    assert kwargs.get("ex") == 259_200  # 3-day TTL preserved
