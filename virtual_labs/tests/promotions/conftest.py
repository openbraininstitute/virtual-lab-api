from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import (
    PromotionCode,
    PromotionCodeRedemptionAttempt,
    PromotionCodeUsage,
)
from virtual_labs.infrastructure.redis import get_redis
from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab,
    get_headers,
    get_user_id_from_test_auth,
)


class PromotionCodeFactory:
    """Factory for creating promotion codes with picky default values."""

    @staticmethod
    def create_valid_code(
        code: str = "TESTCODE2025",
        credits_amount: float = 1000.0,
        max_uses_per_user: int = 1,
        max_total_uses: int | None = None,
        active: bool = True,
        valid_days_ago: int = 1,
        valid_days_ahead: int = 30,
    ) -> Dict[str, object]:
        """Create a valid promotion code data dictionary."""
        now = datetime.now(timezone.utc)
        return {
            "code": code.upper(),
            "description": f"Test promotion code {code}",
            "credits_amount": credits_amount,
            "validity_period_days": valid_days_ago + valid_days_ahead,
            "max_uses_per_user_per_period": max_uses_per_user,
            "max_total_uses": max_total_uses,
            "current_total_uses": 0,
            "active": active,
            "valid_from": now - timedelta(days=valid_days_ago),
            "valid_until": now + timedelta(days=valid_days_ahead),
            "created_by": uuid4(),
        }

    @staticmethod
    def create_expired_code(code: str = "EXPIRED2024") -> Dict[str, object]:
        """Create an expired promotion code."""
        now = datetime.now(timezone.utc)
        return {
            "code": code.upper(),
            "description": "Expired promotion code",
            "credits_amount": 500.0,
            "validity_period_days": 30,
            "max_uses_per_user_per_period": 1,
            "max_total_uses": None,
            "current_total_uses": 0,
            "active": True,
            "valid_from": now - timedelta(days=60),
            "valid_until": now - timedelta(days=1),
            "created_by": uuid4(),
        }

    @staticmethod
    def create_future_code(code: str = "FUTURE2026") -> Dict[str, object]:
        """Create a promotion code that starts in the future."""
        now = datetime.now(timezone.utc)
        return {
            "code": code.upper(),
            "description": "Future promotion code",
            "credits_amount": 750.0,
            "validity_period_days": 30,
            "max_uses_per_user_per_period": 1,
            "max_total_uses": None,
            "current_total_uses": 0,
            "active": True,
            "valid_from": now + timedelta(days=7),
            "valid_until": now + timedelta(days=37),
            "created_by": uuid4(),
        }

    @staticmethod
    def create_inactive_code(code: str = "INACTIVE") -> Dict[str, object]:
        """Create an inactive promotion code."""
        now = datetime.now(timezone.utc)
        return {
            "code": code.upper(),
            "description": "Inactive promotion code",
            "credits_amount": 300.0,
            "validity_period_days": 30,
            "max_uses_per_user_per_period": 1,
            "max_total_uses": None,
            "current_total_uses": 0,
            "active": False,
            "valid_from": now - timedelta(days=1),
            "valid_until": now + timedelta(days=29),
            "created_by": uuid4(),
        }

    @staticmethod
    def create_limited_code(
        code: str = "LIMITED100",
        max_total_uses: int = 100,
        current_uses: int = 0,
    ) -> Dict[str, object]:
        """Create a promotion code with total usage limit."""
        now = datetime.now(timezone.utc)
        return {
            "code": code.upper(),
            "description": "Limited use promotion code",
            "credits_amount": 200.0,
            "validity_period_days": 30,
            "max_uses_per_user_per_period": 1,
            "max_total_uses": max_total_uses,
            "current_total_uses": current_uses,
            "active": True,
            "valid_from": now - timedelta(days=1),
            "valid_until": now + timedelta(days=29),
            "created_by": uuid4(),
        }


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for tests."""
    async for session in default_session_factory():
        yield session


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis, None]:
    """Provide a Redis client for tests."""
    client = await get_redis()
    yield client
    # Cleanup: flush rate limit keys after each test
    await client.delete("promotion_code:redeem:*")


@pytest_asyncio.fixture
async def mock_virtual_lab(
    async_test_client: AsyncClient,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Create a mock virtual lab for testing.
    Ensures cleanup happens whether test passes or fails.
    """
    response = await create_mock_lab(async_test_client)
    assert response.status_code == 200
    lab_data: Dict[str, Any] = response.json()["data"]["virtual_lab"]
    lab_id: str = lab_data["id"]

    try:
        yield lab_data
    finally:
        # Cleanup virtual lab whether test passed or failed
        try:
            await cleanup_resources(async_test_client, lab_id)
        except Exception as e:
            # Log but don't fail the test if cleanup fails
            print(f"Warning: Failed to cleanup virtual lab {lab_id}: {e}")


@pytest_asyncio.fixture
async def test_user_id(async_test_client: AsyncClient) -> UUID:
    """Get the test user ID from authentication."""
    headers = get_headers()
    user_id = await get_user_id_from_test_auth(headers["Authorization"])
    return user_id


@pytest_asyncio.fixture
async def valid_promotion_code(
    db_session: AsyncSession,
) -> AsyncGenerator[PromotionCode, None]:
    """Create and persist a valid promotion code in the database."""
    code_data = PromotionCodeFactory.create_valid_code()
    promotion_code = PromotionCode(**code_data)
    db_session.add(promotion_code)
    await db_session.commit()
    await db_session.refresh(promotion_code)
    yield promotion_code

    # Cleanup
    await db_session.execute(
        delete(PromotionCodeUsage).where(
            PromotionCodeUsage.promotion_code_id == promotion_code.id
        )
    )
    await db_session.execute(
        delete(PromotionCodeRedemptionAttempt).where(
            PromotionCodeRedemptionAttempt.code_attempted == promotion_code.code
        )
    )
    await db_session.execute(
        delete(PromotionCode).where(PromotionCode.id == promotion_code.id)
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def expired_promotion_code(
    db_session: AsyncSession,
) -> AsyncGenerator[PromotionCode, None]:
    """Create and persist an expired promotion code in the database."""
    code_data = PromotionCodeFactory.create_expired_code()
    promotion_code = PromotionCode(**code_data)
    db_session.add(promotion_code)
    await db_session.commit()
    await db_session.refresh(promotion_code)
    yield promotion_code

    # Cleanup
    await db_session.execute(
        delete(PromotionCodeRedemptionAttempt).where(
            PromotionCodeRedemptionAttempt.code_attempted == promotion_code.code
        )
    )
    await db_session.execute(
        delete(PromotionCode).where(PromotionCode.id == promotion_code.id)
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def inactive_promotion_code(
    db_session: AsyncSession,
) -> AsyncGenerator[PromotionCode, None]:
    """Create and persist an inactive promotion code in the database."""
    code_data = PromotionCodeFactory.create_inactive_code()
    promotion_code = PromotionCode(**code_data)
    db_session.add(promotion_code)
    await db_session.commit()
    await db_session.refresh(promotion_code)
    yield promotion_code

    # Cleanup
    await db_session.execute(
        delete(PromotionCodeRedemptionAttempt).where(
            PromotionCodeRedemptionAttempt.code_attempted == promotion_code.code
        )
    )
    await db_session.execute(
        delete(PromotionCode).where(PromotionCode.id == promotion_code.id)
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def future_promotion_code(
    db_session: AsyncSession,
) -> AsyncGenerator[PromotionCode, None]:
    """Create and persist a future promotion code in the database."""
    code_data = PromotionCodeFactory.create_future_code()
    promotion_code = PromotionCode(**code_data)
    db_session.add(promotion_code)
    await db_session.commit()
    await db_session.refresh(promotion_code)
    yield promotion_code

    # Cleanup
    await db_session.execute(
        delete(PromotionCodeRedemptionAttempt).where(
            PromotionCodeRedemptionAttempt.code_attempted == promotion_code.code
        )
    )
    await db_session.execute(
        delete(PromotionCode).where(PromotionCode.id == promotion_code.id)
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def limited_promotion_code(
    db_session: AsyncSession,
) -> AsyncGenerator[PromotionCode, None]:
    """Create and persist a promotion code with usage limit."""
    code_data = PromotionCodeFactory.create_limited_code(
        max_total_uses=2, current_uses=0
    )
    promotion_code = PromotionCode(**code_data)
    db_session.add(promotion_code)
    await db_session.commit()
    await db_session.refresh(promotion_code)
    yield promotion_code

    # Cleanup
    await db_session.execute(
        delete(PromotionCodeUsage).where(
            PromotionCodeUsage.promotion_code_id == promotion_code.id
        )
    )
    await db_session.execute(
        delete(PromotionCodeRedemptionAttempt).where(
            PromotionCodeRedemptionAttempt.code_attempted == promotion_code.code
        )
    )
    await db_session.execute(
        delete(PromotionCode).where(PromotionCode.id == promotion_code.id)
    )
    await db_session.commit()


@pytest.fixture
def mock_accounting_success() -> AsyncMock:
    """Mock successful accounting service response."""
    mock_response = Mock()
    mock_response.id = str(uuid4())
    return mock_response


@pytest.fixture
def mock_accounting_failure() -> Exception:
    """Mock accounting service failure."""
    from http import HTTPStatus

    from virtual_labs.core.exceptions.accounting_error import (
        AccountingError,
        AccountingErrorValue,
    )

    return AccountingError(
        type=AccountingErrorValue.TOP_UP_VIRTUAL_LAB_ACCOUNT_ERROR,
        message="Insufficient funds in accounting system",
        http_status_code=HTTPStatus.BAD_REQUEST,
    )


@pytest_asyncio.fixture
async def cleanup_redis_rate_limits(redis_client: Redis) -> AsyncGenerator[None, None]:
    """Cleanup Redis rate limit keys before and after tests."""
    # Cleanup before test
    pattern = "promotion_code:redeem:*"
    keys = await redis_client.keys(pattern)
    if keys:
        await redis_client.delete(*keys)

    yield

    # Cleanup after test
    keys = await redis_client.keys(pattern)
    if keys:
        await redis_client.delete(*keys)


class VirtualLabManager:
    """
    Manager for creating and cleaning up multiple virtual labs in tests.
    Ensures all labs are cleaned up even if test fails.
    """

    def __init__(self, client: AsyncClient) -> None:
        self.client = client
        self.lab_ids: list[str] = []

    async def create_lab(self, username: str = "test") -> Dict[str, Any]:
        """Create a virtual lab and track it for cleanup."""
        response = await create_mock_lab(self.client, username)
        assert response.status_code == 200
        lab_data: Dict[str, Any] = response.json()["data"]["virtual_lab"]
        self.lab_ids.append(lab_data["id"])
        return lab_data

    async def cleanup_all(self) -> None:
        """Clean up all created labs."""
        for lab_id in self.lab_ids:
            try:
                await cleanup_resources(self.client, lab_id)
            except Exception as e:
                print(f"Warning: Failed to cleanup virtual lab {lab_id}: {e}")
        self.lab_ids.clear()


@pytest_asyncio.fixture
async def virtual_lab_manager(
    async_test_client: AsyncClient,
) -> AsyncGenerator[VirtualLabManager, None]:
    """
    Fixture for tests that need to create multiple virtual labs.
    Automatically cleans up all labs at the end.
    """
    manager = VirtualLabManager(async_test_client)
    try:
        yield manager
    finally:
        await manager.cleanup_all()
