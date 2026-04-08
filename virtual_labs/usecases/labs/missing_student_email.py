from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import Project


async def get_missing_student_emails(
    session: AsyncSession, virtual_lab_id: UUID, provided_emails: list[str]
) -> list[str]:
    email_set = set(provided_emails)

    stmt = select(Project.student_email).where(
        Project.virtual_lab_id == virtual_lab_id, Project.student_email.in_(email_set)
    )

    result = await session.scalars(stmt)
    existing_emails = set(result.all())

    return list(email_set - existing_emails)
