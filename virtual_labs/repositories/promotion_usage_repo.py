"""
Repository for promotion code usage operations.
Handles recording and tracking promotion code redemptions.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from virtual_labs.domain.promotion import PromotionUsageFilters, UsageHistoryFilters
from virtual_labs.infrastructure.db.models import (
    PromotionCodeRedemptionAttempt,
    PromotionCodeUsage,
    PromotionCodeUsageStatus,
)


async def create_usage(
    db: AsyncSession,
    promotion_code_id: UUID,
    user_id: UUID,
    virtual_lab_id: UUID,
    credits_granted: int,
    status: PromotionCodeUsageStatus,
) -> PromotionCodeUsage:
    """
    Create a new promotion code usage record.

    Args:
        db: Database session
        promotion_code_id: Promotion code UUID
        user_id: User UUID
        virtual_lab_id: Virtual lab UUID
        credits_granted: Amount of credits granted
        status: Initial status (usually 'pending')

    Returns:
        Created PromotionCodeUsage
    """
    usage = PromotionCodeUsage(
        promotion_code_id=promotion_code_id,
        user_id=user_id,
        virtual_lab_id=virtual_lab_id,
        credits_granted=credits_granted,
        status=status,
    )

    db.add(usage)
    await db.flush()
    await db.refresh(usage)
    return usage


async def update_status(
    db: AsyncSession,
    usage_id: UUID,
    status: PromotionCodeUsageStatus,
    accounting_transaction_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> PromotionCodeUsage:
    """
    Update the status of a promotion code usage record.

    Args:
        db: Database session
        usage_id: Usage record UUID
        status: New status
        accounting_transaction_id: Transaction ID from accounting system
        error_message: Error message if failed

    Returns:
        Updated PromotionCodeUsage
    """
    usage = await db.get(PromotionCodeUsage, usage_id)
    if usage is None:
        raise ValueError(f"Usage record {usage_id} not found")

    usage.status = status
    if accounting_transaction_id:
        usage.accounting_transaction_id = accounting_transaction_id
    if error_message:
        usage.error_message = error_message

    await db.flush()
    await db.refresh(usage)
    return usage


async def get_usage_count_in_period(
    db: AsyncSession,
    user_id: UUID,
    promotion_code_id: UUID,
    virtual_lab_id: UUID,
    period_start: datetime,
    period_end: datetime,
) -> int:
    """
    Get count of user's redemptions for a promotion code within a time period.
    Only counts pending and completed redemptions (not failed ones).

    Args:
        db: Database session
        user_id: User UUID
        promotion_code_id: Promotion code UUID
        virtual_lab_id: Virtual lab UUID
        period_start: Start of period
        period_end: End of period

    Returns:
        Count of redemptions
    """
    result = await db.scalar(
        select(func.count())
        .select_from(PromotionCodeUsage)
        .where(
            and_(
                PromotionCodeUsage.user_id == user_id,
                PromotionCodeUsage.promotion_code_id == promotion_code_id,
                PromotionCodeUsage.virtual_lab_id == virtual_lab_id,
                PromotionCodeUsage.redeemed_at >= period_start,
                PromotionCodeUsage.redeemed_at <= period_end,
                PromotionCodeUsage.status.in_(
                    [
                        PromotionCodeUsageStatus.PENDING,
                        PromotionCodeUsageStatus.COMPLETED,
                    ]
                ),
            )
        )
    )
    return result or 0


async def get_user_usage_history(
    db: AsyncSession, user_id: UUID, filters: UsageHistoryFilters
) -> tuple[List[PromotionCodeUsage], int]:
    """
    Get user's promotion code redemption history.

    Args:
        db: Database session
        user_id: User UUID
        filters: Filter and pagination parameters

    Returns:
        Tuple of (list of usages, total count)
    """

    conditions = [PromotionCodeUsage.user_id == user_id]

    if filters.virtual_lab_id:
        conditions.append(PromotionCodeUsage.virtual_lab_id == filters.virtual_lab_id)

    if filters.status:
        conditions.append(PromotionCodeUsage.status == filters.status)

    count = (
        await db.scalar(
            select(func.count())
            .select_from(PromotionCodeUsage)
            .where(and_(*conditions))
        )
        or 0
    )

    query = (
        select(PromotionCodeUsage)
        .where(and_(*conditions))
        .options(joinedload(PromotionCodeUsage.promotion_code))
        .options(joinedload(PromotionCodeUsage.virtual_lab))
        .order_by(PromotionCodeUsage.redeemed_at.desc())
        .offset(filters.offset)
        .limit(filters.limit)
    )

    result = await db.execute(query)
    usages = list(result.unique().scalars().all())

    return usages, count


async def get_promotion_usage_stats(
    db: AsyncSession,
    promotion_code_id: UUID,
    filters: Optional[PromotionUsageFilters] = None,
) -> Dict[str, Any]:
    """
    Get usage statistics for a promotion code.

    Args:
        db: Database session
        promotion_code_id: Promotion code UUID
        filters: Optional filters for date range and status

    Returns:
        Dictionary with usage statistics
    """
    # Build base conditions
    conditions = [PromotionCodeUsage.promotion_code_id == promotion_code_id]

    if filters:
        if filters.start_date:
            conditions.append(PromotionCodeUsage.redeemed_at >= filters.start_date)
        if filters.end_date:
            conditions.append(PromotionCodeUsage.redeemed_at <= filters.end_date)
        if filters.status:
            conditions.append(PromotionCodeUsage.status == filters.status)

    total = (
        await db.scalar(
            select(func.count())
            .select_from(PromotionCodeUsage)
            .where(and_(*conditions))
        )
        or 0
    )

    completed = (
        await db.scalar(
            select(func.count())
            .select_from(PromotionCodeUsage)
            .where(
                and_(
                    *conditions,
                    PromotionCodeUsage.status == PromotionCodeUsageStatus.COMPLETED,
                )
            )
        )
        or 0
    )

    pending = (
        await db.scalar(
            select(func.count())
            .select_from(PromotionCodeUsage)
            .where(
                and_(
                    *conditions,
                    PromotionCodeUsage.status == PromotionCodeUsageStatus.PENDING,
                )
            )
        )
        or 0
    )

    failed = (
        await db.scalar(
            select(func.count())
            .select_from(PromotionCodeUsage)
            .where(
                and_(
                    *conditions,
                    PromotionCodeUsage.status == PromotionCodeUsageStatus.FAILED,
                )
            )
        )
        or 0
    )

    # Total credits distributed
    total_credits = (
        await db.scalar(
            select(func.sum(PromotionCodeUsage.credits_granted))
            .select_from(PromotionCodeUsage)
            .where(
                and_(
                    *conditions,
                    PromotionCodeUsage.status == PromotionCodeUsageStatus.COMPLETED,
                )
            )
        )
        or 0
    )

    unique_users = (
        await db.scalar(
            select(func.count(func.distinct(PromotionCodeUsage.user_id)))
            .select_from(PromotionCodeUsage)
            .where(and_(*conditions))
        )
        or 0
    )

    unique_labs = (
        await db.scalar(
            select(func.count(func.distinct(PromotionCodeUsage.virtual_lab_id)))
            .select_from(PromotionCodeUsage)
            .where(and_(*conditions))
        )
        or 0
    )

    return {
        "total_redemptions": total,
        "completed": completed,
        "pending": pending,
        "failed": failed,
        "total_credits_distributed": int(total_credits),
        "unique_users": unique_users,
        "unique_virtual_labs": unique_labs,
    }


async def get_recent_redemptions(
    db: AsyncSession, promotion_code_id: UUID, limit: int = 20
) -> List[PromotionCodeUsage]:
    """
    Get recent redemptions for a promotion code.

    Args:
        db: Database session
        promotion_code_id: Promotion code UUID
        limit: Maximum number of records to return

    Returns:
        List of recent PromotionCodeUsage records
    """
    query = (
        select(PromotionCodeUsage)
        .where(PromotionCodeUsage.promotion_code_id == promotion_code_id)
        .options(joinedload(PromotionCodeUsage.virtual_lab))
        .order_by(PromotionCodeUsage.redeemed_at.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    return list(result.unique().scalars().all())


async def record_attempt(
    db: AsyncSession,
    code_attempted: str,
    user_id: UUID,
    virtual_lab_id: Optional[UUID],
    success: bool,
    failure_reason: Optional[str] = None,
) -> None:
    """
    Record a redemption attempt (success or failure) for analytics.

    Args:
        db: Database session
        code_attempted: The code string provided
        user_id: User UUID
        virtual_lab_id: Virtual lab UUID (if provided)
        success: Whether the attempt succeeded
        failure_reason: Reason for failure (if failed)
    """
    attempt = PromotionCodeRedemptionAttempt(
        code_attempted=code_attempted.upper(),
        user_id=user_id,
        virtual_lab_id=virtual_lab_id,
        success=success,
        failure_reason=failure_reason,
    )

    db.add(attempt)
    await db.flush()


async def get_failed_attempts_count(
    db: AsyncSession, user_id: UUID, time_window_minutes: int = 60
) -> int:
    """
    Get count of failed attempts by a user within a time window.
    Useful for rate limiting and fraud detection.

    Args:
        db: Database session
        user_id: User UUID
        time_window_minutes: Time window in minutes

    Returns:
        Count of failed attempts
    """
    from datetime import timedelta

    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)

    result = await db.scalar(
        select(func.count())
        .select_from(PromotionCodeRedemptionAttempt)
        .where(
            and_(
                PromotionCodeRedemptionAttempt.user_id == user_id,
                PromotionCodeRedemptionAttempt.success.is_(False),
                PromotionCodeRedemptionAttempt.attempted_at >= cutoff_time,
            )
        )
    )
    return result or 0


async def get_total_redemptions_count(db: AsyncSession) -> int:
    """Get total count of all redemptions (completed only)."""
    result = await db.scalar(
        select(func.count())
        .select_from(PromotionCodeUsage)
        .where(PromotionCodeUsage.status == PromotionCodeUsageStatus.COMPLETED)
    )
    return result or 0


async def get_total_credits_distributed(db: AsyncSession) -> int:
    """Get total credits distributed across all promotions."""
    result = await db.scalar(
        select(func.sum(PromotionCodeUsage.credits_granted))
        .select_from(PromotionCodeUsage)
        .where(PromotionCodeUsage.status == PromotionCodeUsageStatus.COMPLETED)
    )
    return int(result) if result else 0
