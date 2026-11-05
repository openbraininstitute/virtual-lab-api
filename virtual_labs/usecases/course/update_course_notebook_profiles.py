"""Set a course's allowed notebook profiles."""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseOut, UpdateCourseNotebookProfilesBody
from virtual_labs.infrastructure.db.models import Course
from virtual_labs.infrastructure.kc.grant import AuthUserGrants


async def update_course_notebook_profiles(
    db: AsyncSession,
    course: Course,
    payload: UpdateCourseNotebookProfilesBody,
    user: AuthUserGrants,
) -> VliAppResponse[CourseOut]:
    course.allowed_notebook_profiles = payload.allowed_notebook_profiles
    await db.commit()
    await db.refresh(course)

    logger.info(f"Course {course.id} notebook profiles updated by user {user.id}")

    return VliAppResponse[CourseOut](
        message="Course notebook profiles updated successfully",
        data=CourseOut.model_validate(course),
    )
