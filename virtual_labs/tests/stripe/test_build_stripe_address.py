"""Unit tests for _build_stripe_address — the unified billing-address converter."""

from __future__ import annotations

import pytest

from virtual_labs.domain.billing import BillingAddress
from virtual_labs.repositories.stripe_repo import _build_stripe_address


@pytest.fixture
def full_address() -> BillingAddress:
    return BillingAddress(
        name="Jane Doe",
        line1="123 Main St",
        line2="Apt 4",
        city="Geneva",
        state="GE",
        postal_code="1200",
        country="CH",
    )


@pytest.fixture
def minimal_address() -> BillingAddress:
    """Only the required `country` field is set."""
    return BillingAddress(country="US")


class TestCustomerCreate:
    def test_full_address_populates_all_fields(
        self, full_address: BillingAddress
    ) -> None:
        result = _build_stripe_address(full_address, "customer_create")

        assert isinstance(result, dict)
        assert result["line1"] == "123 Main St"
        assert result["line2"] == "Apt 4"
        assert result["city"] == "Geneva"
        assert result["state"] == "GE"
        assert result["postal_code"] == "1200"
        assert result["country"] == "CH"

    def test_minimal_address_only_sets_country(
        self, minimal_address: BillingAddress
    ) -> None:
        result = _build_stripe_address(minimal_address, "customer_create")

        assert result.get("country") == "US"
        assert "line1" not in result
        assert "line2" not in result
        assert "city" not in result
        assert "state" not in result
        assert "postal_code" not in result

    def test_return_type_is_create_params_address(
        self, full_address: BillingAddress
    ) -> None:
        result = _build_stripe_address(full_address, "customer_create")
        # TypedDicts are plain dicts at runtime
        assert isinstance(result, dict)


class TestCustomerUpdate:
    def test_full_address_populates_all_fields(
        self, full_address: BillingAddress
    ) -> None:
        result = _build_stripe_address(full_address, "customer_update")

        assert result["line1"] == "123 Main St"
        assert result["line2"] == "Apt 4"
        assert result["city"] == "Geneva"
        assert result["state"] == "GE"
        assert result["postal_code"] == "1200"
        assert result["country"] == "CH"

    def test_minimal_address_only_sets_country(
        self, minimal_address: BillingAddress
    ) -> None:
        result = _build_stripe_address(minimal_address, "customer_update")

        assert result.get("country") == "US"
        assert "line1" not in result

    def test_return_type_is_update_params_address(
        self, full_address: BillingAddress
    ) -> None:
        result = _build_stripe_address(full_address, "customer_update")
        assert isinstance(result, dict)


class TestTaxCalculation:
    def test_full_address_populates_all_fields(
        self, full_address: BillingAddress
    ) -> None:
        result = _build_stripe_address(full_address, "tax_calculation")

        assert result["country"] == "CH"
        assert result["line1"] == "123 Main St"
        assert result["line2"] == "Apt 4"
        assert result["city"] == "Geneva"
        assert result["state"] == "GE"
        assert result["postal_code"] == "1200"

    def test_minimal_address_sets_country_as_required_field(
        self, minimal_address: BillingAddress
    ) -> None:
        result = _build_stripe_address(minimal_address, "tax_calculation")

        # country is always set (required by Stripe Tax API)
        assert result["country"] == "US"
        assert "line1" not in result

    def test_empty_country_defaults_to_empty_string(self) -> None:
        """BillingAddress requires country, but if somehow empty, fallback is ''."""
        # country validator requires min_length=2, so we test the converter logic
        # by constructing a BillingAddress with a valid country then overriding
        addr = BillingAddress(country="CH")
        # Simulate edge case: country is falsy after construction
        object.__setattr__(addr, "country", "")

        result = _build_stripe_address(addr, "tax_calculation")
        assert result["country"] == ""

    def test_return_type_is_tax_params_address(
        self, full_address: BillingAddress
    ) -> None:
        result = _build_stripe_address(full_address, "tax_calculation")
        assert isinstance(result, dict)


class TestCrossTargetConsistency:
    """Verify that all targets produce the same field values for shared fields."""

    def test_shared_fields_match_across_targets(
        self, full_address: BillingAddress
    ) -> None:
        create = _build_stripe_address(full_address, "customer_create")
        update = _build_stripe_address(full_address, "customer_update")
        tax = _build_stripe_address(full_address, "tax_calculation")

        assert create["line1"] == update["line1"] == tax["line1"]
        assert create["line2"] == update["line2"] == tax["line2"]
        assert create["city"] == update["city"] == tax["city"]
        assert create["state"] == update["state"] == tax["state"]
        assert create["postal_code"] == update["postal_code"] == tax["postal_code"]

    def test_country_present_in_all_targets_when_set(
        self, full_address: BillingAddress
    ) -> None:
        create = _build_stripe_address(full_address, "customer_create")
        update = _build_stripe_address(full_address, "customer_update")
        tax = _build_stripe_address(full_address, "tax_calculation")

        assert create["country"] == "CH"
        assert update["country"] == "CH"
        assert tax["country"] == "CH"

    def test_none_optional_fields_are_omitted_customer_create(self) -> None:
        """Fields that are None on BillingAddress should not appear in the result."""
        addr = BillingAddress(country="DE")
        result = _build_stripe_address(addr, "customer_create")
        for key in ("line1", "line2", "city", "state", "postal_code"):
            assert key not in result, f"{key} should be absent for customer_create"

    def test_none_optional_fields_are_omitted_customer_update(self) -> None:
        """Fields that are None on BillingAddress should not appear in the result."""
        addr = BillingAddress(country="DE")
        result = _build_stripe_address(addr, "customer_update")
        for key in ("line1", "line2", "city", "state", "postal_code"):
            assert key not in result, f"{key} should be absent for customer_update"

    def test_none_optional_fields_are_omitted_tax_calculation(self) -> None:
        """Fields that are None on BillingAddress should not appear in the result."""
        addr = BillingAddress(country="DE")
        result = _build_stripe_address(addr, "tax_calculation")
        for key in ("line1", "line2", "city", "state", "postal_code"):
            assert key not in result, f"{key} should be absent for tax_calculation"
