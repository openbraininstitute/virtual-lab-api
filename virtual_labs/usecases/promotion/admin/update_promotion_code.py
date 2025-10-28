"""Admin use case for updating a promotion code."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.promotion import PromotionCodeDetail, PromotionCodeUpdate
from virtual_labs.repositories import promotion_repo


async def update_promotion_code(
    db: AsyncSession,
    promotion_id: UUID,
    update_data: PromotionCodeUpdate,
) -> PromotionCodeDetail:
    """
    Update an existing promotion code (admin only).
    Only allows updating safe fields.

    Args:
        db: Database session
        promotion_id: Promotion code UUID
        update_data: Update data

    Returns:
        Updated PromotionCodeDetail

    Raises:
        PromotionNotFoundError: If promotion not found
    """
    promotion = await promotion_repo.update_promotion(
        db=db,
        promotion_id=promotion_id,
        update_data=update_data,
    )

    await db.commit()
    await db.refresh(promotion)

    return PromotionCodeDetail.model_validate(promotion)
