from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from sqlalchemy.orm import Session
from virtual_labs.core.exceptions.api_error import VlmError, VlmErrorCode
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from http import HTTPStatus
from loguru import logger


def create_virtual_lab(db: Session, lab: domain.VirtualLabCreate) -> models.VirtualLab:
    try:
        return repository.create_virtual_lab(db, lab)
    except IntegrityError:
        raise VlmError(
            message="Another virtual lab with same name already exists",
            error_code=VlmErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
        )
    except SQLAlchemyError as error:
        logger.error(
            "Virtual lab could not be created due to an unknown database error {}".format(
                type(error)
            )
        )

        raise VlmError(
            message="Virtual lab could not be saved to the database",
            error_code=VlmErrorCode.OTHER,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except Exception as error:
        logger.error(
            "Virtual lab could not be created due to an unknown error {}".format(error)
        )

        raise VlmError(
            message="Virtual lab could not be created",
            error_code=VlmErrorCode.OTHER,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
