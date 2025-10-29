"""
Repository for promotion code operations.
Handles CRUD operations and queries for promotion codes.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.promotion_error import PromotionNotFoundError
from virtual_labs.domain.promotion import (
    PromotionCodeCreate,
    PromotionCodeListFilters,
    PromotionCodeUpdate,
)
from virtual_labs.infrastructure.db.models import PromotionCode


async def get_by_code(
    db: AsyncSession, code: str, for_update: bool = False
) -> Optional[PromotionCode]:
    """
    Get active promotion code by code string.
    If multiple codes with same name exist, returns the currently valid and active one.
    Priority: active codes within validity period, then future codes, then most recent.

    Args:
        db: Database session
        code: Promotion code string
        for_update: Whether to lock the row for update (for concurrent safety)

    Returns:
        PromotionCode if found, None otherwise
    """
    now = datetime.now(timezone.utc)

    # Query for active codes with the given name, ordered by priority:
    # 1. Currently valid (active, within period)
    # 2. Future valid (active, starts in future)
    # 3. Most recently created
    query = (
        select(PromotionCode)
        .where(
            and_(
                PromotionCode.code == code.upper(),
                PromotionCode.active.is_(True),
            )
        )
        .order_by(
            # Prioritize currently valid codes
            (
                (PromotionCode.valid_from <= now) & (PromotionCode.valid_until >= now)
            ).desc(),
            # Then future codes
            PromotionCode.valid_from.asc(),
            # Then most recent
            PromotionCode.created_at.desc(),
        )
        .limit(1)
    )

    if for_update:
        query = query.with_for_update()

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_by_id(
    db: AsyncSession, promotion_id: UUID, for_update: bool = False
) -> Optional[PromotionCode]:
    """
    Get promotion code by ID.

    Args:
        db: Database session
        promotion_id: Promotion code UUID
        for_update: Whether to lock the row for update

    Returns:
        PromotionCode if found, None otherwise
    """
    if for_update:
        query = (
            select(PromotionCode)
            .where(PromotionCode.id == promotion_id)
            .with_for_update()
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    return await db.get(PromotionCode, promotion_id)


async def get_by_id_or_raise(db: AsyncSession, promotion_id: UUID) -> PromotionCode:
    """
    Get promotion code by ID or raise exception if not found.

    Args:
        db: Database session
        promotion_id: Promotion code UUID

    Returns:
        PromotionCode

    Raises:
        PromotionNotFoundError: If promotion not found
    """
    promotion = await get_by_id(db, promotion_id)
    if promotion is None:
        raise PromotionNotFoundError(code=str(promotion_id))
    return promotion


async def create(
    db: AsyncSession,
    promotion_data: PromotionCodeCreate,
    created_by: Optional[UUID] = None,
) -> PromotionCode:
    """
    Create a new promotion code.
    Allows duplicate codes with different validity periods for tracking and analytics.

    Args:
        db: Database session
        promotion_data: Promotion code creation data
        created_by: User ID who created the promotion

    Returns:
        Created PromotionCode
    """
    promotion = PromotionCode(
        code=promotion_data.code.upper(),
        description=promotion_data.description,
        credits_amount=promotion_data.credits_amount,
        validity_period_days=promotion_data.validity_period_days,
        max_uses_per_user_per_period=promotion_data.max_uses_per_user_per_period,
        max_total_uses=promotion_data.max_total_uses,
        active=promotion_data.active,
        valid_from=promotion_data.valid_from,
        valid_until=promotion_data.valid_until,
        created_by=created_by,
        current_total_uses=0,
    )

    db.add(promotion)
    await db.flush()
    await db.refresh(promotion)
    return promotion


async def update_promotion(
    db: AsyncSession, promotion_id: UUID, update_data: PromotionCodeUpdate
) -> PromotionCode:
    """
    Update an existing promotion code.
    Only allows updating safe fields (description, active, valid_until, max_total_uses).

    Args:
        db: Database session
        promotion_id: Promotion code UUID
        update_data: Update data

    Returns:
        Updated PromotionCode

    Raises:
        PromotionNotFoundError: If promotion not found
    """
    promotion = await get_by_id_or_raise(db, promotion_id)

    # Only update provided fields
    if update_data.description is not None:
        promotion.description = update_data.description
    if update_data.active is not None:
        promotion.active = update_data.active
    if update_data.valid_until is not None:
        promotion.valid_until = update_data.valid_until
    if update_data.max_total_uses is not None:
        promotion.max_total_uses = update_data.max_total_uses

    await db.flush()
    await db.refresh(promotion)
    return promotion


async def deactivate(db: AsyncSession, promotion_id: UUID) -> PromotionCode:
    """
    Deactivate a promotion code (soft delete).

    Args:
        db: Database session
        promotion_id: Promotion code UUID

    Returns:
        Deactivated PromotionCode

    Raises:
        PromotionNotFoundError: If promotion not found
    """
    promotion = await get_by_id_or_raise(db, promotion_id)
    promotion.active = False
    await db.flush()
    await db.refresh(promotion)
    return promotion


async def increment_usage_counter(db: AsyncSession, promotion_id: UUID) -> None:
    """
    Atomically increment the usage counter for a promotion code.

    Args:
        db: Database session
        promotion_id: Promotion code UUID
    """
    await db.execute(
        update(PromotionCode)
        .where(PromotionCode.id == promotion_id)
        .values(current_total_uses=PromotionCode.current_total_uses + 1)
    )


async def list_promotions(
    db: AsyncSession, filters: PromotionCodeListFilters
) -> tuple[List[PromotionCode], int]:
    """
    List promotion codes with filters and pagination.

    Args:
        db: Database session
        filters: Filter and pagination parameters

    Returns:
        Tuple of (list of promotions, total count)
    """

    conditions = []

    if filters.active is not None:
        conditions.append(PromotionCode.active == filters.active)

    if filters.search:
        search_term = f"%{filters.search}%"
        conditions.append(
            PromotionCode.code.ilike(search_term),
        )

    count_query = select(func.count()).select_from(PromotionCode)
    if conditions:
        count_query = count_query.where(and_(*conditions))

    total = await db.scalar(count_query) or 0

    data_query = select(PromotionCode)
    if conditions:
        data_query = data_query.where(and_(*conditions))

    data_query = (
        data_query.order_by(PromotionCode.created_at.desc())
        .offset(filters.offset)
        .limit(filters.limit)
    )

    result = await db.execute(data_query)
    promotions = list(result.scalars().all())

    return promotions, total


async def get_active_promotions_count(db: AsyncSession) -> int:
    """Get count of active promotion codes."""
    result = await db.scalar(
        select(func.count())
        .select_from(PromotionCode)
        .where(PromotionCode.active.is_(True))
    )
    return result or 0


async def get_expired_promotions_count(db: AsyncSession) -> int:
    """Get count of expired promotion codes."""
    now = datetime.now(timezone.utc)
    result = await db.scalar(
        select(func.count())
        .select_from(PromotionCode)
        .where(PromotionCode.valid_until < now)
    )
    return result or 0
