"""Admin use case for deactivating a promotion code."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.promotion import PromotionCodeDetail
from virtual_labs.repositories import promotion_repo


async def deactivate_promotion_code(
    db: AsyncSession,
    promotion_id: UUID,
) -> PromotionCodeDetail:
    """
    Deactivate a promotion code (soft delete, admin only).

    Args:
        db: Database session
        promotion_id: Promotion code UUID

    Returns:
        Deactivated PromotionCodeDetail

    Raises:
        PromotionNotFoundError: If promotion not found
    """
    promotion = await promotion_repo.deactivate(db=db, promotion_id=promotion_id)

    await db.commit()
    await db.refresh(promotion)

    return PromotionCodeDetail.model_validate(promotion)
