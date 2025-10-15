"""
Helper utilities and additional test scenarios for promotion code testing.
These helpers can be used by integration tests or other test modules.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import (
    PromotionCode,
    PromotionCodeRedemptionAttempt,
    PromotionCodeUsage,
    PromotionCodeUsageStatus,
)


class PromotionTestHelper:
    """Helper class for promotion code testing operations."""

    @staticmethod
    async def get_usage_count_for_code(
        db_session: AsyncSession, promotion_code_id: UUID
    ) -> int:
        """Get the number of times a promotion code has been used."""
        result = await db_session.execute(
            select(PromotionCodeUsage).where(
                PromotionCodeUsage.promotion_code_id == promotion_code_id,
                PromotionCodeUsage.status == PromotionCodeUsageStatus.COMPLETED,
            )
        )
        usages = result.scalars().all()
        return len(usages)

    @staticmethod
    async def get_failed_attempts_count(db_session: AsyncSession, code: str) -> int:
        """Get the number of failed redemption attempts for a code."""
        result = await db_session.execute(
            select(PromotionCodeRedemptionAttempt).where(
                PromotionCodeRedemptionAttempt.code_attempted == code,
                PromotionCodeRedemptionAttempt.success.is_(False),
            )
        )
        attempts = result.scalars().all()
        return len(attempts)

    @staticmethod
    async def get_successful_attempts_count(db_session: AsyncSession, code: str) -> int:
        """Get the number of successful redemption attempts for a code."""
        result = await db_session.execute(
            select(PromotionCodeRedemptionAttempt).where(
                PromotionCodeRedemptionAttempt.code_attempted == code,
                PromotionCodeRedemptionAttempt.success.is_(True),
            )
        )
        attempts = result.scalars().all()
        return len(attempts)

    @staticmethod
    async def get_user_redemptions(
        db_session: AsyncSession, user_id: UUID
    ) -> List[PromotionCodeUsage]:
        """Get all redemptions for a specific user."""
        result = await db_session.execute(
            select(PromotionCodeUsage)
            .where(PromotionCodeUsage.user_id == user_id)
            .order_by(PromotionCodeUsage.redeemed_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_virtual_lab_redemptions(
        db_session: AsyncSession, virtual_lab_id: UUID
    ) -> List[PromotionCodeUsage]:
        """Get all redemptions for a specific virtual lab."""
        result = await db_session.execute(
            select(PromotionCodeUsage)
            .where(PromotionCodeUsage.virtual_lab_id == virtual_lab_id)
            .order_by(PromotionCodeUsage.redeemed_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def is_code_redeemable(db_session: AsyncSession, code: str) -> bool:
        """Check if a promotion code can currently be redeemed."""
        result = await db_session.execute(
            select(PromotionCode).where(PromotionCode.code == code.upper())
        )
        promotion = result.scalar_one_or_none()

        if not promotion:
            return False

        now = datetime.now(timezone.utc)

        # Check all conditions
        if not promotion.active:
            return False

        if now < promotion.valid_from or now > promotion.valid_until:
            return False

        if promotion.max_total_uses is not None:
            if promotion.current_total_uses >= promotion.max_total_uses:
                return False

        return True

    @staticmethod
    async def get_code_statistics(
        db_session: AsyncSession, code: str
    ) -> Dict[str, int]:
        """Get statistics for a promotion code."""
        result = await db_session.execute(
            select(PromotionCode).where(PromotionCode.code == code.upper())
        )
        promotion = result.scalar_one_or_none()

        if not promotion:
            return {
                "total_uses": 0,
                "completed": 0,
                "pending": 0,
                "failed": 0,
                "unique_users": 0,
                "unique_virtual_labs": 0,
            }

        # Get usage statistics
        usage_result = await db_session.execute(
            select(PromotionCodeUsage).where(
                PromotionCodeUsage.promotion_code_id == promotion.id
            )
        )
        usages = list(usage_result.scalars().all())

        completed = sum(
            1 for u in usages if u.status == PromotionCodeUsageStatus.COMPLETED
        )
        pending = sum(1 for u in usages if u.status == PromotionCodeUsageStatus.PENDING)
        failed = sum(1 for u in usages if u.status == PromotionCodeUsageStatus.FAILED)

        unique_users = len(set(u.user_id for u in usages))
        unique_virtual_labs = len(set(u.virtual_lab_id for u in usages))

        return {
            "total_uses": len(usages),
            "completed": completed,
            "pending": pending,
            "failed": failed,
            "unique_users": unique_users,
            "unique_virtual_labs": unique_virtual_labs,
        }

    @staticmethod
    def create_date_range_codes(
        base_code: str, num_codes: int = 5
    ) -> List[Dict[str, object]]:
        """
        Create multiple promotion codes with sequential date ranges.
        Useful for testing code selection logic.
        """
        codes = []
        now = datetime.now(timezone.utc)

        for i in range(num_codes):
            code_data = {
                "code": f"{base_code}_{i}",
                "description": f"Test code {i}",
                "credits_amount": 100.0 * (i + 1),
                "validity_period_days": 30,
                "max_uses_per_user_per_period": 1,
                "max_total_uses": None,
                "current_total_uses": 0,
                "active": True,
                "valid_from": now + timedelta(days=30 * i),
                "valid_until": now + timedelta(days=30 * (i + 1)),
            }
            codes.append(code_data)

        return codes

    @staticmethod
    async def verify_redemption_audit_trail(
        db_session: AsyncSession,
        promotion_code_id: UUID,
        expected_user_id: UUID,
        expected_virtual_lab_id: UUID,
    ) -> bool:
        """
        Verify that a redemption has proper audit trail.
        Checks that usage and attempt records exist.
        """
        # Check usage record
        usage_result = await db_session.execute(
            select(PromotionCodeUsage).where(
                PromotionCodeUsage.promotion_code_id == promotion_code_id,
                PromotionCodeUsage.user_id == expected_user_id,
                PromotionCodeUsage.virtual_lab_id == expected_virtual_lab_id,
            )
        )
        usage = usage_result.scalar_one_or_none()

        if not usage:
            return False

        # Get the promotion code
        promotion_result = await db_session.execute(
            select(PromotionCode).where(PromotionCode.id == promotion_code_id)
        )
        promotion = promotion_result.scalar_one()

        # Check attempt record
        attempt_result = await db_session.execute(
            select(PromotionCodeRedemptionAttempt)
            .where(
                PromotionCodeRedemptionAttempt.code_attempted == promotion.code,
                PromotionCodeRedemptionAttempt.user_id == expected_user_id,
                PromotionCodeRedemptionAttempt.virtual_lab_id
                == expected_virtual_lab_id,
            )
            .order_by(PromotionCodeRedemptionAttempt.attempted_at.desc())
            .limit(1)
        )
        attempt = attempt_result.scalar_one_or_none()

        return attempt is not None

    @staticmethod
    async def cleanup_all_promotion_data(
        db_session: AsyncSession,
    ) -> None:
        """
        Clean up all promotion-related test data.
        Use with caution - this deletes ALL promotion data.
        """
        from sqlalchemy import delete

        # Delete in order to respect foreign key constraints
        await db_session.execute(delete(PromotionCodeRedemptionAttempt))
        await db_session.execute(delete(PromotionCodeUsage))
        await db_session.execute(delete(PromotionCode))
        await db_session.commit()


async def assert_redemption_success(
    db_session: AsyncSession,
    response_data: Dict[str, object],
    expected_code: str,
    expected_credits: int,
) -> None:
    """
    Assert that a redemption was successful with expected values.

    Args:
        db_session: Database session
        response_data: Response data from the API
        expected_code: Expected promotion code
        expected_credits: Expected credits amount
    """
    assert response_data["promotion_code"] == expected_code
    assert response_data["credits_granted"] == expected_credits
    assert response_data["status"] == PromotionCodeUsageStatus.COMPLETED.value
    assert "redemption_id" in response_data
    assert "redeemed_at" in response_data

    # Verify in database
    redemption_id = UUID(str(response_data["redemption_id"]))
    usage = await db_session.get(PromotionCodeUsage, redemption_id)
    assert usage is not None
    assert usage.status == PromotionCodeUsageStatus.COMPLETED


async def assert_redemption_failed(
    response_data: Dict[str, object],
    expected_status_code: int,
    expected_message_contains: str,
) -> None:
    """
    Assert that a redemption failed with expected error.

    Args:
        response_data: Response data from the API
        expected_status_code: Expected HTTP status code
        expected_message_contains: Expected substring in error message
    """
    assert "message" in response_data
    assert expected_message_contains.lower() in str(response_data["message"]).lower()
