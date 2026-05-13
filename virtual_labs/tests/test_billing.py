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
    billing_address_to_profile_attributes,
    billing_address_to_stripe,
    is_tax_enabled_for_country,
    quote_expires_at_end_of_today,
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
    lab_id = response.json()["data"]["virtual_lab"]["id"]

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
