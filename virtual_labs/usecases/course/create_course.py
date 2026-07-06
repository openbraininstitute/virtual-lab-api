"""Create a course.

The create-course endpoint does NOT provision virtual labs or projects.
It merely assigns an existing virtual lab and an existing project (template)
to a new course record.
"""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseCreateBody, CourseOut
from virtual_labs.infrastructure.db.models import (
    Course,
    CourseStatus,
    Project,
    VirtualLab,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.settings import settings
from virtual_labs.usecases import accounting as accounting_cases
from virtual_labs.usecases.labs.get_virtual_lab_or_raise import (
    get_virtual_lab_or_raise,
)


async def _validate_virtual_lab(db: AsyncSession, virtual_lab_id: UUID) -> VirtualLab:
    """Ensure the virtual lab exists, is not deleted, and is a course lab."""
    vlab = await get_virtual_lab_or_raise(db, virtual_lab_id)
    if vlab.owner_id != settings.MULTIPLE_VLABS_ALLOWED_USER_ID:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.FORBIDDEN,
            message="Virtual lab is not a course lab",
        )
    return vlab


async def _validate_project(
    db: AsyncSession, project_id: UUID, virtual_lab_id: UUID
) -> Project:
    """Ensure the project exists, belongs to the given virtual lab, and is not deleted."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.virtual_lab_id == virtual_lab_id,
            Project.deleted.is_(False),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=(f"Project {project_id} not found in virtual lab {virtual_lab_id}"),
        )
    return project


async def create_course(
    db: AsyncSession,
    payload: CourseCreateBody,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseOut]:
    # Validate that the referenced virtual lab and project exist
    vlab = await _validate_virtual_lab(db, payload.virtual_lab_id)
    await _validate_project(db, payload.template_project_id, payload.virtual_lab_id)

    db_course = Course(
        virtual_lab_id=payload.virtual_lab_id,
        institution_id=payload.institution_id,
        template_project_id=payload.template_project_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        last_drop_date=payload.last_drop_date,
        status=CourseStatus.DRAFT,
        credits_per_seat=settings.CREDITS_PER_SEAT,
    )
    db.add(db_course)

    try:
        await db.commit()
        await db.refresh(db_course)
    except IntegrityError as err:
        await db.rollback()
        logger.error(f"DB integrity error during course creation: {err}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
            message="Course creation failed due to a conflict (virtual lab may already have a course)",
        ) from err
    except SQLAlchemyError as err:
        await db.rollback()
        logger.error(f"DB error during course creation: {err}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Course creation failed",
        ) from err

    # Post-commit: refresh vlab (now has course relationship) and fund template project
    await db.refresh(vlab)
    await accounting_cases.fund_project(
        virtual_lab_id=vlab.id,
        project_id=payload.template_project_id,
        amount=settings.CREDITS_PER_SEAT,
    )

    return VliAppResponse[CourseOut](
        message="Course created successfully",
        data=CourseOut.model_validate(db_course),
    )
