from http import HTTPStatus

from loguru import logger
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.institution import InstitutionOut, InstitutionUpdate
from virtual_labs.infrastructure.db.models import Institution


async def update_institution(
    session: AsyncSession,
    institution_id: UUID4,
    payload: InstitutionUpdate,
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

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise VliError(
            message="No fields to update",
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )

    for field, value in update_data.items():
        setattr(institution, field, value)

    try:
        await session.commit()
        await session.refresh(institution)
    except IntegrityError as error:
        await session.rollback()
        logger.error(
            f"Institution {institution_id} could not be updated due to database error: {error}"
        )
        raise VliError(
            message="Another institution with the same name already exists",
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
        )

    return InstitutionOut.model_validate(institution)
