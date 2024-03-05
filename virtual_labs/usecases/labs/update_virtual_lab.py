from pydantic import UUID4
from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from sqlalchemy.orm import Session
from virtual_labs.core.exceptions.api_error import VlmError, VlmErrorCode
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, NoResultFound
from http import HTTPStatus
from loguru import logger


def update_virtual_lab(
    db: Session, lab_id: UUID4, lab: domain.VirtualLabUpdate
) -> models.VirtualLab:
    try:
        return repository.update_virtual_lab(db, lab_id, lab)
    except IntegrityError:
        raise VlmError(
            message="Another virtual lab with same name already exists",
            error_code=VlmErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
        )
    except NoResultFound:
        raise VlmError(
            message="Virtual lab not found",
            error_code=VlmErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    except SQLAlchemyError:
        logger.error(
            "Virtual lab {} update could not be processed for unknown database error".format(
                lab_id
            )
        )

        raise VlmError(
            message="Virtual lab could not be saved to the database",
            error_code=VlmErrorCode.OTHER,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
