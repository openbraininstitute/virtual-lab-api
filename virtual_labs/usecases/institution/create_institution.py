from http import HTTPStatus

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
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
    except IntegrityError as error:
        await session.rollback()
        logger.error(f"Institution could not be created due to database error: {error}")
        raise VliError(
            message="Institution could not be created",
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
        )

    return InstitutionOut.model_validate(institution)
