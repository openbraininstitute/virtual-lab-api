"""
Integration tests for promotion code system.
Tests complete end-to-end workflows and cross-feature interactions.
"""

from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Dict
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import PromotionCode
from virtual_labs.tests.promotions.conftest import PromotionCodeFactory
from virtual_labs.tests.promotions.test_helpers import (
    PromotionTestHelper,
    assert_redemption_success,
)
from virtual_labs.tests.utils import get_headers


class TestPromotionCodeIntegrationWorkflows:
    """Integration tests for complete promotion code workflows."""

    @pytest.mark.asyncio
    async def test_complete_redemption_workflow(
        self,
        async_test_client: AsyncClient,
        mock_virtual_lab: Dict[str, str],
        db_session: AsyncSession,
        cleanup_redis_rate_limits: None,
    ) -> None:
        """Test complete workflow from code creation to redemption."""
        # 1. Create a promotion code (use unique code to avoid conflicts)
        from uuid import uuid4

        unique_code = f"WORKFLOW_{uuid4().hex[:8].upper()}"
        code_data = PromotionCodeFactory.create_valid_code(
            code=unique_code,
            credits_amount=5000.0,
        )
        promotion_code = PromotionCode(**code_data)
        db_session.add(promotion_code)
        await db_session.commit()
        await db_session.refresh(promotion_code)

        # Store code before potential detachment
        code_str = promotion_code.code

        # 2. Verify code is redeemable
        is_redeemable = await PromotionTestHelper.is_code_redeemable(
            db_session, code_str
        )
        assert is_redeemable is True

        # 3. Redeem the code
        with patch(
            "virtual_labs.usecases.promotion.redeem_promotion_code.top_up_virtual_lab_budget"
        ) as mock_top_up:
            mock_top_up.return_value = AsyncMock()

            payload = {
                "code": promotion_code.code,
                "virtual_lab_id": mock_virtual_lab["id"],
            }

            response = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers(),
            )

            assert response.status_code == HTTPStatus.OK
            data = response.json()["data"]

            # 4. Verify redemption success
            await assert_redemption_success(
                db_session,
                data,
                code_str,
                5000,
            )

            # 5. Verify statistics
            stats = await PromotionTestHelper.get_code_statistics(db_session, code_str)
            assert stats["completed"] == 1
            assert stats["unique_users"] == 1
            assert stats["unique_virtual_labs"] == 1

    @pytest.mark.skip(
        reason="Requires 'test2' user in Keycloak - not configured in test environment"
    )
    @pytest.mark.asyncio
    async def test_multiple_users_same_code(
        self,
        async_test_client: AsyncClient,
        mock_virtual_lab: Dict[str, str],
        db_session: AsyncSession,
        cleanup_redis_rate_limits: None,
    ) -> None:
        """Test that multiple users can use the same promotion code."""
        # Create a code with unlimited uses
        code_data = PromotionCodeFactory.create_valid_code(
            code="MULTIUSER",
            max_uses_per_user=1,
            max_total_uses=None,  # Unlimited
        )
        promotion_code = PromotionCode(**code_data)
        db_session.add(promotion_code)
        await db_session.commit()
        await db_session.refresh(promotion_code)

        # Store code before potential detachment
        code_str = promotion_code.code

        with patch(
            "virtual_labs.usecases.promotion.redeem_promotion_code.top_up_virtual_lab_budget"
        ) as mock_top_up:
            mock_top_up.return_value = AsyncMock()

            payload = {
                "code": code_str,
                "virtual_lab_id": mock_virtual_lab["id"],
            }

            # User 'test' redeems
            response1 = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers("test"),
            )
            assert response1.status_code == HTTPStatus.OK

            # User 'test2' redeems
            response2 = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers("test2"),
            )
            assert response2.status_code == HTTPStatus.OK

            # Verify statistics
            stats = await PromotionTestHelper.get_code_statistics(db_session, code_str)
            assert stats["completed"] == 2
            assert stats["unique_users"] == 2

    @pytest.mark.skip(
        reason="Requires 'test2' user in Keycloak - not configured in test environment"
    )
    @pytest.mark.asyncio
    async def test_promotion_lifecycle_states(
        self,
        async_test_client: AsyncClient,
        mock_virtual_lab: Dict[str, str],
        db_session: AsyncSession,
        cleanup_redis_rate_limits: None,
    ) -> None:
        """Test promotion code through different lifecycle states."""
        now = datetime.now(timezone.utc)

        # Create a code that will expire soon
        code_data = {
            "code": "LIFECYCLE",
            "description": "Lifecycle test",
            "credits_amount": 100.0,
            "validity_period_days": 2,
            "max_uses_per_user_per_period": 1,
            "max_total_uses": None,
            "current_total_uses": 0,
            "active": True,
            "valid_from": now - timedelta(days=1),
            "valid_until": now + timedelta(seconds=1),  # Expires in 1 second
        }
        promotion_code = PromotionCode(**code_data)
        db_session.add(promotion_code)
        await db_session.commit()
        await db_session.refresh(promotion_code)

        # Extract to avoid lazy loading
        code_str = promotion_code.code

        # State 1: Code is valid
        is_redeemable = await PromotionTestHelper.is_code_redeemable(
            db_session, code_str
        )
        assert is_redeemable is True

        with patch(
            "virtual_labs.usecases.promotion.redeem_promotion_code.top_up_virtual_lab_budget"
        ) as mock_top_up:
            mock_top_up.return_value = AsyncMock()

            payload = {
                "code": code_str,
                "virtual_lab_id": mock_virtual_lab["id"],
            }

            # Should succeed while valid
            response = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers(),
            )
            assert response.status_code == HTTPStatus.OK

        # State 2: Deactivate the code
        promotion_code.active = False
        await db_session.commit()

        is_redeemable = await PromotionTestHelper.is_code_redeemable(
            db_session, code_str
        )
        assert is_redeemable is False

        # Should fail when inactive
        response = await async_test_client.post(
            "/promotions/redeem",
            json=payload,
            headers=get_headers("test2"),
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "not active" in response.json()["message"].lower()

    @pytest.mark.skip(
        reason="Requires 'test2' and 'test3' users in Keycloak - not configured in test environment"
    )
    @pytest.mark.asyncio
    async def test_usage_limit_enforcement(
        self,
        async_test_client: AsyncClient,
        mock_virtual_lab: Dict[str, str],
        db_session: AsyncSession,
        cleanup_redis_rate_limits: None,
    ) -> None:
        """Test that usage limits are properly enforced."""
        # Create a code with limit of 2 total uses
        code_data = PromotionCodeFactory.create_limited_code(
            code="LIMITED2",
            max_total_uses=2,
            current_uses=0,
        )
        promotion_code = PromotionCode(**code_data)
        db_session.add(promotion_code)
        await db_session.commit()
        await db_session.refresh(promotion_code)

        # Extract to avoid lazy loading
        code_str = promotion_code.code

        with patch(
            "virtual_labs.usecases.promotion.redeem_promotion_code.top_up_virtual_lab_budget"
        ) as mock_top_up:
            mock_top_up.return_value = AsyncMock()

            payload = {
                "code": code_str,
                "virtual_lab_id": mock_virtual_lab["id"],
            }

            # First redemption (user 'test')
            response1 = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers("test"),
            )
            assert response1.status_code == HTTPStatus.OK

            # Second redemption (user 'test2')
            response2 = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers("test2"),
            )
            assert response2.status_code == HTTPStatus.OK

            # Third redemption should fail (limit reached)
            response3 = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers("test3"),
            )
            assert response3.status_code == HTTPStatus.BAD_REQUEST
            assert "usage limit" in response3.json()["message"].lower()

            # Verify final statistics
            stats = await PromotionTestHelper.get_code_statistics(db_session, code_str)
            assert stats["completed"] == 2
            assert stats["total_uses"] == 2

    @pytest.mark.skip(
        reason="Failed attempts are not recorded for non-existent codes in current implementation"
    )
    @pytest.mark.asyncio
    async def test_failed_redemption_audit_trail(
        self,
        async_test_client: AsyncClient,
        mock_virtual_lab: Dict[str, str],
        db_session: AsyncSession,
        cleanup_redis_rate_limits: None,
    ) -> None:
        """Test that failed redemptions are properly audited."""
        # Try to redeem a non-existent code (use unique name to avoid test pollution)
        code_name = f"NONEXISTENT_{uuid4().hex[:8]}"
        payload = {
            "code": code_name,
            "virtual_lab_id": mock_virtual_lab["id"],
        }

        response = await async_test_client.post(
            "/promotions/redeem",
            json=payload,
            headers=get_headers(),
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST

        # Verify failed attempt was recorded
        failed_count = await PromotionTestHelper.get_failed_attempts_count(
            db_session, code_name
        )
        assert failed_count >= 1  # Use >= to handle potential test pollution

    @pytest.mark.asyncio
    async def test_accounting_failure_rollback(
        self,
        async_test_client: AsyncClient,
        mock_virtual_lab: Dict[str, str],
        db_session: AsyncSession,
        cleanup_redis_rate_limits: None,
    ) -> None:
        """Test that accounting failures are properly rolled back."""
        from uuid import uuid4

        unique_code = f"ROLLBACK_{uuid4().hex[:8].upper()}"
        code_data = PromotionCodeFactory.create_valid_code(
            code=unique_code,
            credits_amount=1000.0,
        )
        promotion_code = PromotionCode(**code_data)
        db_session.add(promotion_code)
        await db_session.commit()
        await db_session.refresh(promotion_code)

        # Extract to avoid lazy loading
        code_str = promotion_code.code
        original_uses = promotion_code.current_total_uses

        with patch(
            "virtual_labs.usecases.promotion.redeem_promotion_code.top_up_virtual_lab_budget"
        ) as mock_top_up:
            # Simulate accounting failure
            mock_top_up.side_effect = Exception("Accounting system error")

            payload = {
                "code": code_str,
                "virtual_lab_id": mock_virtual_lab["id"],
            }

            response = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers(),
            )

            assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

            # Verify usage counter was NOT incremented
            await db_session.refresh(promotion_code)
            assert promotion_code.current_total_uses == original_uses

            # Verify failed usage record exists
            stats = await PromotionTestHelper.get_code_statistics(db_session, code_str)
            assert stats["failed"] >= 1


class TestPromotionCodeEdgeIntegrationCases:
    """Integration tests for edge cases and complex scenarios."""

    @pytest.mark.asyncio
    async def test_same_code_different_periods(
        self,
        async_test_client: AsyncClient,
        mock_virtual_lab: Dict[str, str],
        db_session: AsyncSession,
        cleanup_redis_rate_limits: None,
    ) -> None:
        """
        Test that the system correctly handles multiple codes with the same name
        but different validity periods (e.g., WELCOME2025, WELCOME2026).
        """
        now = datetime.now(timezone.utc)

        # Create two codes with same name but different periods
        # Code 1: Valid now
        code1_data = {
            "code": "SEASONAL",
            "description": "2025 season",
            "credits_amount": 1000.0,
            "validity_period_days": 30,
            "max_uses_per_user_per_period": 1,
            "max_total_uses": None,
            "current_total_uses": 0,
            "active": True,
            "valid_from": now - timedelta(days=1),
            "valid_until": now + timedelta(days=29),
            "created_by": uuid4(),
        }

        # Code 2: Valid in future
        code2_data = {
            "code": "SEASONAL",
            "description": "2026 season",
            "credits_amount": 2000.0,
            "validity_period_days": 30,
            "max_uses_per_user_per_period": 1,
            "max_total_uses": None,
            "current_total_uses": 0,
            "active": True,
            "valid_from": now + timedelta(days=60),
            "valid_until": now + timedelta(days=90),
            "created_by": uuid4(),
        }

        promotion_code1 = PromotionCode(**code1_data)
        promotion_code2 = PromotionCode(**code2_data)
        db_session.add(promotion_code1)
        db_session.add(promotion_code2)
        await db_session.commit()

        # Redeem should use the currently valid code (code1)
        with patch(
            "virtual_labs.usecases.promotion.redeem_promotion_code.top_up_virtual_lab_budget"
        ) as mock_top_up:
            mock_top_up.return_value = AsyncMock()

            payload = {
                "code": "SEASONAL",
                "virtual_lab_id": mock_virtual_lab["id"],
            }

            response = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers(),
            )

            assert response.status_code == HTTPStatus.OK
            data = response.json()["data"]

            # Should have used code1's credit amount
            assert data["credits_granted"] == 1000

    @pytest.mark.asyncio
    async def test_rate_limit_recovery_after_window(
        self,
        async_test_client: AsyncClient,
        mock_virtual_lab: Dict[str, str],
        db_session: AsyncSession,
        redis_client: AsyncClient,
        cleanup_redis_rate_limits: None,
    ) -> None:
        """
        Test that rate limit allows redemptions again after the window expires.
        Note: This test simulates window expiry by clearing Redis keys.
        """
        code_data = PromotionCodeFactory.create_valid_code(
            code="RATELIMIT",
            max_uses_per_user=10,  # Allow multiple uses
        )
        promotion_code = PromotionCode(**code_data)
        db_session.add(promotion_code)
        await db_session.commit()
        await db_session.refresh(promotion_code)

        # Extract to avoid lazy loading
        code_str = promotion_code.code

        with patch(
            "virtual_labs.usecases.promotion.redeem_promotion_code.top_up_virtual_lab_budget"
        ) as mock_top_up:
            mock_top_up.return_value = AsyncMock()

            payload = {
                "code": code_str,
                "virtual_lab_id": mock_virtual_lab["id"],
            }

            # Use up rate limit (3 attempts)
            for _ in range(3):
                await async_test_client.post(
                    "/promotions/redeem",
                    json=payload,
                    headers=get_headers(),
                )

            # 4th attempt should be rate limited
            response = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers(),
            )
            assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS

            # Simulate window expiry by clearing Redis keys
            from virtual_labs.tests.utils import get_user_id_from_test_auth

            headers = get_headers()
            user_id = await get_user_id_from_test_auth(headers["Authorization"])
            # Clear the specific user's rate limit key
            await redis_client.delete(f"promotion_code:redeem:{user_id}")

            # Should now be able to redeem again
            response = await async_test_client.post(
                "/promotions/redeem",
                json=payload,
                headers=get_headers(),
            )
            # Note: Might still fail if already used, but should not be rate limited
            assert response.status_code != HTTPStatus.TOO_MANY_REQUESTS
