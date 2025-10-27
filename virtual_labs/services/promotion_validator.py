"""
Promotion code validation service.
Provides validation logic for promotion code redemptions.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.promotion_error import (
    PromotionAlreadyUsedError,
    PromotionExpiredError,
    PromotionNotActiveError,
    PromotionNotFoundError,
    PromotionNotYetValidError,
    PromotionUsageLimitReachedError,
)
from virtual_labs.infrastructure.db.models import PromotionCode
from virtual_labs.repositories import promotion_repo, promotion_usage_repo


class PromotionValidator:
    """Validator for promotion code operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def validate_code_exists(self, code: str) -> PromotionCode:
        """
        Validate that promotion code exists.

        Args:
            code: Promotion code string

        Returns:
            PromotionCode

        Raises:
            PromotionNotFoundError: If code doesn't exist
        """
        promotion = await promotion_repo.get_by_code(self.db, code)
        if promotion is None:
            raise PromotionNotFoundError(code=code)
        return promotion

    def validate_code_active(self, promotion: PromotionCode) -> None:
        """
        Validate that promotion code is active.

        Args:
            promotion: PromotionCode instance

        Raises:
            PromotionNotActiveError: If code is not active
        """
        if not promotion.active:
            raise PromotionNotActiveError(code=promotion.code)

    def validate_code_validity_period(self, promotion: PromotionCode) -> None:
        """
        Validate that current time is within promotion code validity period.

        Args:
            promotion: PromotionCode instance

        Raises:
            PromotionNotYetValidError: If code is not yet valid
            PromotionExpiredError: If code has expired
        """
        now = datetime.now(timezone.utc)

        if now < promotion.valid_from:
            raise PromotionNotYetValidError(
                code=promotion.code, valid_from=promotion.valid_from
            )

        if now > promotion.valid_until:
            raise PromotionExpiredError(
                code=promotion.code, expired_at=promotion.valid_until
            )

    def validate_total_usage_limit(self, promotion: PromotionCode) -> None:
        """
        Validate that promotion code hasn't reached its total usage limit.

        Args:
            promotion: PromotionCode instance

        Raises:
            PromotionUsageLimitReachedError: If total usage limit reached
        """
        if promotion.max_total_uses is not None:
            if promotion.current_total_uses >= promotion.max_total_uses:
                raise PromotionUsageLimitReachedError(
                    code=promotion.code, max_uses=promotion.max_total_uses
                )

    async def validate_user_period_limit(
        self,
        promotion: PromotionCode,
        user_id: UUID,
        virtual_lab_id: UUID,
    ) -> None:
        """
        Validate that user hasn't exceeded usage limit for this promotion within the validity period.

        Args:
            promotion: PromotionCode instance
            user_id: User UUID
            virtual_lab_id: Virtual lab UUID

        Raises:
            PromotionAlreadyUsedError: If user has exceeded usage limit for this period
        """
        # Count user's usage within the validity period
        usage_count = await promotion_usage_repo.get_usage_count_in_period(
            db=self.db,
            user_id=user_id,
            promotion_code_id=promotion.id,
            virtual_lab_id=virtual_lab_id,
            period_start=promotion.valid_from,
            period_end=promotion.valid_until,
        )

        if usage_count >= promotion.max_uses_per_user_per_period:
            raise PromotionAlreadyUsedError(
                code=promotion.code,
                user_id=user_id,
                virtual_lab_id=virtual_lab_id,
            )

    async def validate_all(
        self,
        code: str,
        user_id: UUID,
        virtual_lab_id: UUID,
    ) -> PromotionCode:
        """
        Run all validations for promotion code redemption.
        Validates in order of expense (cheapest checks first).

        Args:
            code: Promotion code string
            user_id: User UUID
            virtual_lab_id: Virtual lab UUID

        Returns:
            PromotionCode if all validations pass

        Raises:
            Various PromotionError subclasses for different validation failures
        """
        # 1. Check code exists (cheapest - single query)
        promotion = await self.validate_code_exists(code)

        # 2. Check code is active (cheap - in-memory)
        self.validate_code_active(promotion)

        # 3. Check validity period (cheap - date comparison)
        self.validate_code_validity_period(promotion)

        # 4. Check total usage limit (cheap - in-memory)
        self.validate_total_usage_limit(promotion)

        # 5. Check user period limit (most expensive - requires DB query)
        await self.validate_user_period_limit(promotion, user_id, virtual_lab_id)

        return promotion

    async def can_redeem(
        self,
        code: str,
        user_id: UUID,
        virtual_lab_id: UUID,
    ) -> tuple[bool, List[str], Optional[PromotionCode]]:
        """
        Check if a promotion code can be redeemed without raising exceptions.
        Returns detailed information about validation results.

        Args:
            code: Promotion code string
            user_id: User UUID
            virtual_lab_id: Virtual lab UUID

        Returns:
            Tuple of (can_redeem: bool, reasons: list of failure reasons, promotion: PromotionCode or None)
        """
        reasons: List[str] = []

        try:
            # Check code exists
            promotion = await promotion_repo.get_by_code(self.db, code)
            if promotion is None:
                reasons.append("Code not found")
                return False, reasons, None

            # Check active
            if not promotion.active:
                reasons.append("Code is not active")

            # Check validity period
            now = datetime.now(timezone.utc)
            if now < promotion.valid_from:
                reasons.append("Code is not yet valid")
            if now > promotion.valid_until:
                reasons.append("Code has expired")

            # Check total usage limit
            if promotion.max_total_uses is not None:
                if promotion.current_total_uses >= promotion.max_total_uses:
                    reasons.append("Code usage limit reached")

            # Check user period limit
            usage_count = await promotion_usage_repo.get_usage_count_in_period(
                db=self.db,
                user_id=user_id,
                promotion_code_id=promotion.id,
                virtual_lab_id=virtual_lab_id,
                period_start=promotion.valid_from,
                period_end=promotion.valid_until,
            )

            if usage_count >= promotion.max_uses_per_user_per_period:
                reasons.append(
                    "You have already used this code for this virtual lab in the current period"
                )

            can_redeem = len(reasons) == 0
            return can_redeem, reasons, promotion

        except Exception as e:
            reasons.append(f"Validation error: {str(e)}")
            return False, reasons, None
