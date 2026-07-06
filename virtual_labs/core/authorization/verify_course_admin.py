from http import HTTPStatus
from typing import Optional

from fastapi import Depends
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Course
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants


async def resolve_course(
    course_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
) -> Optional[Course]:
    result = await session.execute(select(Course).where(Course.id == course_id))
    return result.scalar_one_or_none()


async def verify_course_admin(
    course: Optional[Course] = Depends(resolve_course),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> tuple[AuthUserGrants, Course]:
    user, _ = auth
    if course is None or not user.is_vlab_admin(course.virtual_lab_id):
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.FORBIDDEN,
            message="Not authorized to perform this action",
        )
    return user, course
