from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from virtual_labs.services.credit_converter import (
    DEFAULT_EXCHANGE_RATES,
    CreditConverter,
)


@pytest.fixture
def mock_exchange_rate_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_all_rates = AsyncMock(
        return_value={
            "chf": Decimal("0.05"),
            "usd": Decimal("0.055"),
            "eur": Decimal("0.048"),
        }
    )
    return repo


@pytest.mark.asyncio
async def test_currency_to_credits(mock_exchange_rate_repo: AsyncMock) -> None:
    converter = CreditConverter(exchange_rate_repo=mock_exchange_rate_repo)

    # Test CHF conversion
    credits = await converter.currency_to_credits(1000, "chf")
    assert credits == Decimal("200")  # 10 chf / 0.05 chf/credit = 200 credits

    # Test USD conversion
    credits = await converter.currency_to_credits(1100, "usd")
    assert credits == Decimal("200")  # 11 usd / 0.055 usd/credit = 200 credits


@pytest.mark.asyncio
async def test_credits_to_currency(mock_exchange_rate_repo: AsyncMock) -> None:
    converter = CreditConverter(exchange_rate_repo=mock_exchange_rate_repo)

    # Test CHF conversion
    amount = await converter.credits_to_currency(200, "chf")
    assert amount == Decimal("1000")  # 200 credits * 0.05 chf/credit = 10 chf

    # Test USD conversion
    amount = await converter.credits_to_currency(200, "usd")
    assert amount == Decimal("1100")  # 200 credits * 0.055 usd/credit = 11 usd


@pytest.mark.asyncio
async def test_unsupported_currency(mock_exchange_rate_repo: AsyncMock) -> None:
    converter = CreditConverter(exchange_rate_repo=mock_exchange_rate_repo)

    with pytest.raises(ValueError, match="Unsupported currency: jpy"):
        await converter.currency_to_credits(100, "jpy")


@pytest.mark.asyncio
async def test_refresh_rates(mock_exchange_rate_repo: AsyncMock) -> None:
    converter = CreditConverter(exchange_rate_repo=mock_exchange_rate_repo)

    # Initial load
    await converter.get_exchange_rate("chf")
    assert mock_exchange_rate_repo.get_all_rates.call_count == 1

    # Should use cached rates
    await converter.get_exchange_rate("usd")
    assert mock_exchange_rate_repo.get_all_rates.call_count == 1

    # Force refresh
    await converter.refresh_rates()
    assert mock_exchange_rate_repo.get_all_rates.call_count == 2


@pytest.mark.asyncio
async def test_fallback_to_defaults() -> None:
    # Repository returns empty rates
    repo = AsyncMock()
    repo.get_all_rates = AsyncMock(return_value={})

    converter = CreditConverter(exchange_rate_repo=repo)

    # Should fall back to defaults
    rate = await converter.get_exchange_rate("chf")
    assert rate == DEFAULT_EXCHANGE_RATES["chf"]
