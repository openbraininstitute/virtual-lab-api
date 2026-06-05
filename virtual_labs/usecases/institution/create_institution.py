from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.institution import InstitutionCreate, InstitutionOut
from virtual_labs.infrastructure.db.models import Institution


async def create_institution(
    session: AsyncSession,
    payload: InstitutionCreate,
) -> InstitutionOut:
    institution = Institution(
        name=payload.name,
        contact_email=payload.contact_email,
    )
    session.add(institution)

    try:
        await session.commit()
        await session.refresh(institution)
    except IntegrityError:
        await session.rollback()
        existing = await session.execute(
            select(Institution).where(Institution.name == payload.name)
        )
        institution = existing.scalar_one()

    return InstitutionOut.model_validate(institution)
