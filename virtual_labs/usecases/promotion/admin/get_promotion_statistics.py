"""Admin use case for getting promotion usage statistics and analytics."""

from typing import List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.promotion import (
    PromotionAnalytics,
    PromotionCodeStatistics,
    PromotionCodeUsageOut,
    PromotionCodeUsageStats,
    PromotionUsageFilters,
)
from virtual_labs.repositories import promotion_repo, promotion_usage_repo


async def get_promotion_usage_statistics(
    db: AsyncSession,
    promotion_id: UUID,
    filters: PromotionUsageFilters,
) -> PromotionCodeUsageStats:
    """
    Get detailed usage statistics for a specific promotion code (admin only).

    Args:
        db: Database session
        promotion_id: Promotion code UUID
        filters: Filters for date range and pagination

    Returns:
        PromotionCodeUsageStats with statistics and recent redemptions

    Raises:
        PromotionNotFoundError: If promotion not found
    """
    # Verify promotion exists
    promotion = await promotion_repo.get_by_id_or_raise(
        db=db, promotion_id=promotion_id
    )

    # Get statistics
    stats = await promotion_usage_repo.get_promotion_usage_stats(
        db=db,
        promotion_code_id=promotion_id,
        filters=filters,
    )

    # Get recent redemptions
    recent = await promotion_usage_repo.get_recent_redemptions(
        db=db,
        promotion_code_id=promotion_id,
        limit=filters.limit,
    )

    # Convert to output schema
    recent_out: List[PromotionCodeUsageOut] = []
    for usage in recent:
        recent_out.append(
            PromotionCodeUsageOut(
                id=usage.id,
                promotion_code_id=usage.promotion_code_id,
                promotion_code=promotion.code,
                user_id=usage.user_id,
                virtual_lab_id=usage.virtual_lab_id,
                virtual_lab_name=usage.virtual_lab.name if usage.virtual_lab else None,
                credits_granted=usage.credits_granted,
                status=usage.status,
                redeemed_at=usage.redeemed_at,
                accounting_transaction_id=usage.accounting_transaction_id,
                error_message=usage.error_message,
            )
        )

    return PromotionCodeUsageStats(
        promotion_code=promotion.code,
        statistics=PromotionCodeStatistics(**stats),
        recent_redemptions=recent_out,
    )


async def get_system_analytics(db: AsyncSession) -> PromotionAnalytics:
    """
    Get system-wide promotion analytics (admin only).

    Args:
        db: Database session

    Returns:
        PromotionAnalytics with system-wide statistics
    """
    # Get total promotions count
    from virtual_labs.domain.promotion import PromotionCodeListFilters

    all_filters = PromotionCodeListFilters(limit=1, offset=0)
    _, total_promotions = await promotion_repo.list_promotions(
        db=db, filters=all_filters
    )

    # Get active promotions count
    active_count = await promotion_repo.get_active_promotions_count(db=db)

    # Get expired promotions count
    expired_count = await promotion_repo.get_expired_promotions_count(db=db)

    # Get total redemptions
    total_redemptions = await promotion_usage_repo.get_total_redemptions_count(db=db)

    # Get total credits distributed
    total_credits = await promotion_usage_repo.get_total_credits_distributed(db=db)

    return PromotionAnalytics(
        total_promotions=total_promotions,
        active_promotions=active_count,
        expired_promotions=expired_count,
        total_redemptions=total_redemptions,
        total_credits_distributed=total_credits,
    )
