"""Tests for the volume-based credit converter."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from virtual_labs.services.credit_converter import CreditConverter


def _make_tier(
    *,
    currency: str = "chf",
    min_credits: int = 1,
    max_credits: int | None = None,
    rate: Decimal = Decimal("0.10"),
    discount_pct: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        currency=currency,
        min_credits=min_credits,
        max_credits=max_credits,
        rate=rate,
        discount_pct=discount_pct,
    )


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Mock CreditPackageRateRepository with CHF volume tiers."""
    repo = AsyncMock()
    # Default: return the 1-499 tier
    repo.get_rate_for_credits = AsyncMock(
        return_value=_make_tier(rate=Decimal("0.10"), discount_pct=0)
    )
    repo.get_base_rate = AsyncMock(return_value=Decimal("0.10"))
    repo.get_all_active_rates = AsyncMock(return_value=[])
    return repo


@pytest.mark.asyncio
async def test_flat_rate_conversion(mock_repo: AsyncMock) -> None:
    """Single tier (flat pricing): 100 credits × 0.10 × 100 = 1000 cents."""
    converter = CreditConverter(package_rate_repo=mock_repo)

    amount = await converter.credits_to_currency(100, "chf")
    assert amount == Decimal("1000")


@pytest.mark.asyncio
async def test_volume_discount_conversion(mock_repo: AsyncMock) -> None:
    """Volume tier: 2000 credits × 0.09 × 100 = 18000 cents."""
    mock_repo.get_rate_for_credits = AsyncMock(
        return_value=_make_tier(rate=Decimal("0.09"), discount_pct=10)
    )
    converter = CreditConverter(package_rate_repo=mock_repo)

    result = await converter.convert_credits(2000, "chf")

    assert result.amount == 18000
    assert result.rate == Decimal("0.09")
    assert result.discount_pct == 10
    assert result.base_rate == Decimal("0.10")


@pytest.mark.asyncio
async def test_large_volume_discount(mock_repo: AsyncMock) -> None:
    """50000+ tier: 60000 credits × 0.07 × 100 = 420000 cents."""
    mock_repo.get_rate_for_credits = AsyncMock(
        return_value=_make_tier(rate=Decimal("0.07"), discount_pct=30, max_credits=None)
    )
    converter = CreditConverter(package_rate_repo=mock_repo)

    result = await converter.convert_credits(60000, "chf")

    assert result.amount == 420000
    assert result.rate == Decimal("0.07")
    assert result.discount_pct == 30


@pytest.mark.asyncio
async def test_unsupported_currency_raises(mock_repo: AsyncMock) -> None:
    """No tier found → ValueError."""
    mock_repo.get_rate_for_credits = AsyncMock(return_value=None)
    converter = CreditConverter(package_rate_repo=mock_repo)

    with pytest.raises(ValueError, match="No pricing tier found"):
        await converter.credits_to_currency(100, "jpy")


@pytest.mark.asyncio
async def test_currency_to_credits_uses_base_rate(mock_repo: AsyncMock) -> None:
    """Reverse calculation uses base rate (display only)."""
    mock_repo.get_base_rate = AsyncMock(return_value=Decimal("0.10"))
    converter = CreditConverter(package_rate_repo=mock_repo)

    # 1000 cents / 0.10 / 100 = 100 credits
    credits = await converter.currency_to_credits(1000, "chf")
    assert credits == Decimal("100")


@pytest.mark.asyncio
async def test_get_exchange_rate_returns_base(mock_repo: AsyncMock) -> None:
    """get_exchange_rate returns the base tier rate."""
    mock_repo.get_base_rate = AsyncMock(return_value=Decimal("0.10"))
    converter = CreditConverter(package_rate_repo=mock_repo)

    rate = await converter.get_exchange_rate("chf")
    assert rate == Decimal("0.10")


@pytest.mark.asyncio
async def test_get_exchange_rate_unsupported_currency(mock_repo: AsyncMock) -> None:
    """No base rate → ValueError."""
    mock_repo.get_base_rate = AsyncMock(return_value=None)
    converter = CreditConverter(package_rate_repo=mock_repo)

    with pytest.raises(ValueError, match="Unsupported currency"):
        await converter.get_exchange_rate("xyz")
