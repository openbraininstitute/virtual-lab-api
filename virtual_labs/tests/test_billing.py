from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from virtual_labs.domain.billing import (
    BillingAddress,
    BillingFlow,
    CreateBillingQuoteRequest,
    CreditConversionRequest,
)
from virtual_labs.infrastructure.settings import Settings, settings
from virtual_labs.services.billing import (
    billing_address_to_profile_attributes,
    billing_address_to_stripe,
    is_tax_enabled_for_country,
    quote_expires_at_end_of_today,
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


def test_blank_credit_tax_code_is_disabled() -> None:
    app_settings = cast(Any, Settings)(
        _env_file=None,
        DEPLOYMENT_ENV="development",
        STRIPE_CREDIT_TAX_CODE=" ",
    )

    assert app_settings.STRIPE_CREDIT_TAX_CODE is None


def test_credit_conversion_request_normalizes_currency() -> None:
    request = CreditConversionRequest(credits=100, currency="CHF")

    assert request.currency == "chf"


def test_openapi_exposes_credit_conversion_endpoint() -> None:
    from virtual_labs.api import app

    schema = app.openapi()

    assert "/billing/credit-conversions" in schema["paths"]


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
