from uuid import UUID

from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import Project


async def get_missing_contact_emails(
    session: AsyncSession, virtual_lab_id: UUID, provided_emails: list[EmailStr]
) -> list[EmailStr]:
    email_set = set(provided_emails)

    stmt = select(Project.contact_email).where(
        Project.virtual_lab_id == virtual_lab_id,
        Project.contact_email.in_(email_set),
        ~Project.deleted,
    )

    result = await session.scalars(stmt)
    existing_emails = set(result.all())

    return list(email_set - existing_emails)
