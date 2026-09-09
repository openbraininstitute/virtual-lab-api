"""Create a course.

The create-course endpoint does NOT provision virtual labs or projects.
It merely assigns an existing virtual lab and an existing project (template)
to a new course record.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from decimal import Decimal
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.accounting_error import AccountingError
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.ledger import ledger_container
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


def _as_utc(value: datetime | None) -> datetime | None:
    """Coerce a datetime to UTC-aware (accounting requires AwareDatetime)."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _apply_pro_discount(
    virtual_lab_id: UUID,
    *,
    start_date: datetime | None,
    end_date: datetime | None,
) -> None:
    """Apply the pro discount to the course's virtual lab, aborting on failure.

    The discount validity mirrors the course window: it starts at the course
    start date (or now, if the course has no start date yet) and ends at the
    course end date (open-ended if unset).
    """
    if settings.ACCOUNTING_BASE_URL is None:
        return

    valid_from = _as_utc(start_date) or datetime.now(timezone.utc)
    valid_to = _as_utc(end_date)

    try:
        await accounting_cases.create_virtual_lab_discount(
            virtual_lab_id=virtual_lab_id,
            discount=settings.COURSE_PRO_DISCOUNT,
            valid_from=valid_from,
            valid_to=valid_to,
        )
    except AccountingError as err:
        logger.error(
            f"Failed to apply pro discount for virtual lab {virtual_lab_id}: {err}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=err.http_status_code or HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Course creation failed: could not apply the pro discount",
        ) from err
    except Exception as err:
        logger.exception(
            f"Unexpected error applying pro discount for virtual lab {virtual_lab_id}: {err}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Course creation failed: could not apply the pro discount",
        ) from err


def _make_pro_discount_compensation(
    virtual_lab_id: UUID,
) -> Callable[[], Awaitable[None]]:
    """Undo the pro discount.

    Accounting has no "delete discount" endpoint, so this records a fresh
    discount of 0 to supersede the pro discount.
    """

    async def _undo() -> None:
        try:
            await accounting_cases.create_virtual_lab_discount(
                virtual_lab_id=virtual_lab_id,
                discount=Decimal(0),
                valid_from=datetime.now(timezone.utc),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"Failed to reverse pro discount (apply 0) for virtual lab "
                f"{virtual_lab_id}; reconcile manually: {exc}"
            )

    return _undo


def _make_deplete_compensation(
    virtual_lab_id: UUID, project_id: UUID
) -> Callable[[], Awaitable[None]]:
    """Undo project funding by depleting the granted credits."""

    async def _undo() -> None:
        await accounting_cases.deplete_project_budget(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
        )

    return _undo


async def _fund_template_project(virtual_lab_id: UUID, project_id: UUID) -> None:
    """Grant the template project its per-seat credits, aborting on failure."""
    if settings.ACCOUNTING_BASE_URL is None:
        return

    funded = await accounting_cases.fund_project(
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        amount=settings.CREDITS_PER_SEAT,
    )
    if not funded:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Course creation failed: could not fund the template project",
        )


async def _persist_course(db: AsyncSession, db_course: Course) -> None:
    """Commit the course row, translating DB failures into VliError."""
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


async def create_course(
    db: AsyncSession,
    payload: CourseCreateBody,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseOut]:
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

    # Each accounting side-effect pushes its own compensation before the commit,
    # so if any step (including the commit) fails the ledger unwinds them in LIFO
    # order, aborting creation cleanly.
    async with ledger_container() as comp:
        await _apply_pro_discount(
            vlab.id,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        comp.push(_make_pro_discount_compensation(vlab.id))

        await _fund_template_project(vlab.id, payload.template_project_id)
        comp.push(_make_deplete_compensation(vlab.id, payload.template_project_id))

        await _persist_course(db, db_course)

    await db.refresh(vlab)

    return VliAppResponse[CourseOut](
        message="Course created successfully",
        data=CourseOut.model_validate(db_course),
    )
