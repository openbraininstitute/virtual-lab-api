from http import HTTPStatus
from typing import Optional

from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.institution import InstitutionOut
from virtual_labs.infrastructure.db.models import Institution


async def get_institution_by_id(
    session: AsyncSession,
    institution_id: UUID4,
) -> InstitutionOut:
    result = await session.execute(
        select(Institution).where(Institution.id == institution_id)
    )
    institution = result.scalar_one_or_none()

    if institution is None:
        raise VliError(
            message="Institution not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    return InstitutionOut.model_validate(institution)


async def search_institutions_by_name(
    session: AsyncSession,
    query: Optional[str] = None,
) -> list[InstitutionOut]:
    stmt = select(Institution).order_by(Institution.name)

    if query:
        stmt = stmt.where(Institution.name.ilike(f"%{query}%"))

    result = await session.execute(stmt)
    institutions = result.scalars().all()

    return [InstitutionOut.model_validate(inst) for inst in institutions]
