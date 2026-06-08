"""Shared helper to fetch a virtual lab or raise a 404."""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.db.models import VirtualLab


async def get_virtual_lab_or_raise(
    db: AsyncSession, virtual_lab_id: UUID
) -> VirtualLab:
    """Return the virtual lab if it exists and is not deleted, else raise 404."""
    result = await db.execute(
        select(VirtualLab).where(
            VirtualLab.id == virtual_lab_id,
            VirtualLab.deleted.is_(False),
        )
    )
    vlab = result.scalar_one_or_none()
    if vlab is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Virtual lab {virtual_lab_id} not found",
        )
    return vlab
