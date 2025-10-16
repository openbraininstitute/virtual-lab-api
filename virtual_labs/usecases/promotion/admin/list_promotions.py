"""Admin use case for listing all promotion codes."""

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.promotion import (
    PaginationOut,
    PromotionCodeListFilters,
    PromotionCodeOut,
)
from virtual_labs.repositories import promotion_repo


async def list_promotions(
    db: AsyncSession,
    filters: PromotionCodeListFilters,
) -> tuple[List[PromotionCodeOut], PaginationOut]:
    """
    List all promotion codes with filtering and pagination (admin only).

    Args:
        db: Database session
        filters: Filter and pagination parameters

    Returns:
        Tuple of (list of promotion codes, pagination metadata)
    """
    promotions, total = await promotion_repo.list_promotions(db=db, filters=filters)

    promotion_list = [PromotionCodeOut.model_validate(p) for p in promotions]

    pagination = PaginationOut.create(
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )

    return promotion_list, pagination
