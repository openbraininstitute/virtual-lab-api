"""Admin use case for creating a new promotion code."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.promotion import PromotionCodeCreate, PromotionCodeDetail
from virtual_labs.repositories import promotion_repo


async def create_promotion_code(
    db: AsyncSession,
    promotion_data: PromotionCodeCreate,
    admin_user_id: UUID,
) -> PromotionCodeDetail:
    """
    Create a new promotion code (admin only).

    Args:
        db: Database session
        promotion_data: Promotion code creation data
        admin_user_id: Admin user creating the promotion

    Returns:
        Created PromotionCodeDetail

    Raises:
        PromotionCodeAlreadyExistsError: If code already exists
    """
    promotion = await promotion_repo.create(
        db=db,
        promotion_data=promotion_data,
        created_by=admin_user_id,
    )

    await db.commit()
    await db.refresh(promotion)

    return PromotionCodeDetail.model_validate(promotion)
