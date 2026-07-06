from uuid import UUID

from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import Course, CourseEnrolment


async def get_missing_contact_emails(
    session: AsyncSession, virtual_lab_id: UUID, provided_emails: list[EmailStr]
) -> list[EmailStr]:
    """Return emails from provided_emails that are NOT already enrolled in any course for this vlab."""
    email_set = set(provided_emails)

    stmt = (
        select(CourseEnrolment.contact_email)
        .join(Course, CourseEnrolment.course_id == Course.id)
        .where(
            Course.virtual_lab_id == virtual_lab_id,
            CourseEnrolment.contact_email.in_(email_set),
        )
    )

    result = await session.scalars(stmt)
    existing_emails = set(result.all())

    return list(email_set - existing_emails)
