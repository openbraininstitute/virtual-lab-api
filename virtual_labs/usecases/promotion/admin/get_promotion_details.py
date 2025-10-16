"""Admin use case for getting detailed promotion code information."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.promotion import PromotionCodeDetail
from virtual_labs.repositories import promotion_repo


async def get_promotion_details(
    db: AsyncSession,
    promotion_id: UUID,
) -> PromotionCodeDetail:
    """
    Get detailed information about a promotion code (admin only).

    Args:
        db: Database session
        promotion_id: Promotion code UUID

    Returns:
        PromotionCodeDetail

    Raises:
        PromotionNotFoundError: If promotion not found
    """
    promotion = await promotion_repo.get_by_id_or_raise(
        db=db, promotion_id=promotion_id
    )
    return PromotionCodeDetail.model_validate(promotion)
