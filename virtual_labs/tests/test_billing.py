from datetime import datetime, timezone
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any, AsyncGenerator, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pydantic import ValidationError

from virtual_labs.domain.billing import (
    BillingAddress,
    BillingFlow,
    CreateBillingQuoteRequest,
    TaxBehavior,
    TaxStatus,
)
from virtual_labs.infrastructure.settings import Settings, settings
from virtual_labs.services.billing import (
    BillingQuoteService,
    apply_subscription_discount,
    billing_address_to_profile_attributes,
    billing_address_to_stripe,
    is_tax_enabled_for_country,
    quote_expires_at_end_of_today,
    quote_to_response,
)
from virtual_labs.tests.utils import (
    cleanup_all_user_labs,
    cleanup_resources,
    get_headers,
)

lab_owner_user = "test"
non_member_user = "test-2"


@pytest_asyncio.fixture
async def mock_lab_for_billing(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, str], None]:
    client = async_test_client
    await cleanup_all_user_labs(client, lab_owner_user)
    body = {
        "name": f"Billing Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
    }
    response = await client.post(
        "/virtual-labs",
        json=body,
        headers=get_headers(lab_owner_user),
    )
    assert response.status_code == 200, response.text
    lab_id = response.json()["id"]

    yield client, lab_id

    await cleanup_resources(client, lab_id)


def _quote_body(virtual_lab_id: str) -> dict[str, Any]:
    return {
        "flow": BillingFlow.SUBSCRIPTION.value,
        "currency": "CHF",
        "billing_address": {"country": "CH"},
        "virtual_lab_id": virtual_lab_id,
        "tier_id": str(uuid4()),
        "interval": "month",
    }


def _stub_quote_record(virtual_lab_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        flow=BillingFlow.SUBSCRIPTION,
        subtotal=1000,
        tax_amount=0,
        total=1000,
        currency="chf",
        tax_behavior=TaxBehavior.EXCLUSIVE,
        tax_country="CH",
        tax_status=TaxStatus.NOT_APPLICABLE,
        discount_pct=0,
        expires_at=datetime.now(timezone.utc),
        virtual_lab_id=virtual_lab_id,
    )


def test_billing_address_maps_to_profile_attributes() -> None:
    address = BillingAddress(
        name="Ada Lovelace",
        line1="Rue de Lausanne 1",
        city="Geneva",
        state="GE",
        postal_code="1201",
        country="ch",
    )

    assert billing_address_to_profile_attributes(address) == {
        "country": ["CH"],
        "street": ["Rue de Lausanne 1"],
        "postal_code": ["1201"],
        "locality": ["Geneva"],
        "region": ["GE"],
    }


def test_billing_address_maps_to_stripe_address_without_empty_values() -> None:
    address = BillingAddress(
        line1="Rue de Lausanne 1",
        city="Geneva",
        postal_code="1201",
        country="CH",
    )

    assert billing_address_to_stripe(address) == {
        "line1": "Rue de Lausanne 1",
        "city": "Geneva",
        "postal_code": "1201",
        "country": "CH",
    }


def test_billing_address_accepts_country_only_for_tax_calculation() -> None:
    address = BillingAddress(country="ch")

    assert address.country == "CH"
    assert billing_address_to_stripe(address) == {"country": "CH"}


def test_quote_expiry_is_end_of_today_utc() -> None:
    expires_at = quote_expires_at_end_of_today(
        datetime(2026, 5, 6, 10, 30, tzinfo=timezone.utc)
    )

    assert expires_at == datetime(2026, 5, 6, 23, 59, 59, 999999, tzinfo=timezone.utc)


def test_tax_is_enabled_only_for_configured_countries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "BILLING_TAX_ENABLED", True)
    monkeypatch.setattr(settings, "BILLING_TAX_ENABLED_COUNTRIES", "CH")

    assert is_tax_enabled_for_country("CH") is True
    assert is_tax_enabled_for_country("ch") is True
    assert is_tax_enabled_for_country("FR") is False
    assert is_tax_enabled_for_country(None) is False


def test_tax_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BILLING_TAX_ENABLED", False)
    monkeypatch.setattr(settings, "BILLING_TAX_ENABLED_COUNTRIES", "CH")

    assert is_tax_enabled_for_country("CH") is False


def test_tax_settings_normalize_enabled_countries() -> None:
    app_settings = cast(Any, Settings)(
        _env_file=None,
        DEPLOYMENT_ENV="development",
        BILLING_TAX_ENABLED_COUNTRIES=" ch, CH , de ",
    )

    assert app_settings.BILLING_TAX_ENABLED_COUNTRIES == "CH,DE"


def test_tax_settings_reject_invalid_country_codes() -> None:
    with pytest.raises(ValidationError, match="ISO 3166-1 alpha-2"):
        cast(Any, Settings)(
            _env_file=None,
            DEPLOYMENT_ENV="development",
            BILLING_TAX_ENABLED_COUNTRIES="CHE",
        )


def test_standalone_quote_requires_virtual_lab_and_credits() -> None:
    with pytest.raises(ValidationError):
        CreateBillingQuoteRequest(
            flow=BillingFlow.STANDALONE,
            currency="chf",
            billing_address=BillingAddress(
                line1="Rue de Lausanne 1",
                city="Geneva",
                postal_code="1201",
                country="CH",
            ),
            virtual_lab_id=uuid4(),
        )


def test_subscription_quote_requires_tier_and_interval() -> None:
    with pytest.raises(ValidationError):
        CreateBillingQuoteRequest(
            flow=BillingFlow.SUBSCRIPTION,
            currency="chf",
            billing_address=BillingAddress(
                line1="Rue de Lausanne 1",
                city="Geneva",
                postal_code="1201",
                country="CH",
            ),
            virtual_lab_id=uuid4(),
            credits=10,
        )


@pytest.mark.asyncio
async def test_create_billing_quote_authorizes_payload_virtual_lab(
    mock_lab_for_billing: tuple[AsyncClient, str],
) -> None:
    client, lab_id = mock_lab_for_billing
    body = _quote_body(lab_id)
    stub_quote = _stub_quote_record(lab_id)

    with patch(
        "virtual_labs.routes.billing.BillingQuoteService",
    ) as mock_service_class:
        mock_service_class.return_value.create_quote = AsyncMock(
            return_value=stub_quote
        )

        response = await client.post(
            "/billing/quotes",
            json=body,
            headers=get_headers(lab_owner_user),
        )

    assert response.status_code == HTTPStatus.OK, response.text


@pytest.mark.asyncio
async def test_create_billing_quote_rejects_unauthorized_lab_before_service(
    mock_lab_for_billing: tuple[AsyncClient, str],
) -> None:
    client, lab_id = mock_lab_for_billing
    body = _quote_body(lab_id)

    with patch(
        "virtual_labs.routes.billing.BillingQuoteService",
    ):
        response = await client.post(
            "/billing/quotes",
            json=body,
            headers=get_headers(non_member_user),
        )

    assert response.status_code == HTTPStatus.FORBIDDEN, response.text


def _subscription_quote_payload(interval: str) -> CreateBillingQuoteRequest:
    return CreateBillingQuoteRequest(
        flow=BillingFlow.SUBSCRIPTION,
        currency="chf",
        billing_address=BillingAddress(country="DZ"),
        virtual_lab_id=uuid4(),
        tier_id=uuid4(),
        interval=interval,
    )


def _service_with_tier(tier: SimpleNamespace | None) -> BillingQuoteService:
    """Service with only the collaborator `_resolve_subtotal` needs — no DB,
    no Stripe."""
    service = object.__new__(BillingQuoteService)
    service.subscription_repo = cast(
        Any,
        SimpleNamespace(get_subscription_tier_by_id=AsyncMock(return_value=tier)),
    )
    return service


def _pro_tier() -> SimpleNamespace:
    return SimpleNamespace(
        monthly_amount=5000,
        monthly_discount=2500,
        yearly_amount=55000,
        yearly_discount=27500,
    )


def test_discount_is_subtracted_from_the_list_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENABLE_DISCOUNT", True)

    assert apply_subscription_discount(5000, 2500) == (2500, 50)
    assert apply_subscription_discount(55000, 27500) == (27500, 50)
    assert apply_subscription_discount(5000, 1000) == (4000, 20)


def test_discount_is_ignored_when_the_feature_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENABLE_DISCOUNT", False)

    assert apply_subscription_discount(5000, 2500) == (5000, 0)


def test_absent_or_empty_discount_leaves_the_price_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENABLE_DISCOUNT", True)

    assert apply_subscription_discount(5000, None) == (5000, 0)
    assert apply_subscription_discount(5000, 0) == (5000, 0)
    assert apply_subscription_discount(5000, -100) == (5000, 0)
    assert apply_subscription_discount(0, 2500) == (0, 0)


def test_discount_larger_than_the_price_never_goes_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENABLE_DISCOUNT", True)

    assert apply_subscription_discount(5000, 9000) == (0, 100)


@pytest.mark.asyncio
async def test_subscription_subtotal_applies_the_monthly_discount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENABLE_DISCOUNT", True)
    service = _service_with_tier(_pro_tier())

    subtotal, discount_pct, rate_id = await service._resolve_subtotal(
        _subscription_quote_payload("month")
    )

    assert (subtotal, discount_pct, rate_id) == (2500, 50, None)


@pytest.mark.asyncio
async def test_subscription_subtotal_applies_the_yearly_discount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENABLE_DISCOUNT", True)
    service = _service_with_tier(_pro_tier())

    subtotal, discount_pct, rate_id = await service._resolve_subtotal(
        _subscription_quote_payload("year")
    )

    assert (subtotal, discount_pct, rate_id) == (27500, 50, None)


@pytest.mark.asyncio
async def test_subscription_subtotal_is_the_list_price_without_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENABLE_DISCOUNT", False)
    service = _service_with_tier(_pro_tier())

    subtotal, discount_pct, _ = await service._resolve_subtotal(
        _subscription_quote_payload("month")
    )

    assert (subtotal, discount_pct) == (5000, 0)


@pytest.mark.asyncio
async def test_subscription_subtotal_rejects_an_unknown_tier() -> None:
    service = _service_with_tier(None)

    with pytest.raises(ValueError, match="Subscription plan not found"):
        await service._resolve_subtotal(_subscription_quote_payload("month"))


def test_quote_response_exposes_the_discount_percentage() -> None:
    quote = _stub_quote_record(str(uuid4()))
    quote.subtotal = 2500
    quote.total = 2500
    quote.discount_pct = 50

    response = quote_to_response(cast(Any, quote))

    assert response.discount_pct == 50
    assert response.subtotal == 2500
    assert response.total == 2500


def test_quote_response_defaults_a_null_discount_to_zero() -> None:
    quote = _stub_quote_record(str(uuid4()))
    quote.discount_pct = None

    assert quote_to_response(cast(Any, quote)).discount_pct == 0
