from pydantic import UUID4
from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from sqlalchemy.orm import Session
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, NoResultFound
from http import HTTPStatus
from loguru import logger


def update_virtual_lab(
    db: Session, lab_id: UUID4, lab: domain.VirtualLabUpdate
) -> models.VirtualLab:
    try:
        return repository.update_virtual_lab(db, lab_id, lab)
    except IntegrityError:
        raise VliError(
            message="Another virtual lab with same name already exists",
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
        )
    except NoResultFound:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    except SQLAlchemyError:
        logger.error(
            "Virtual lab {} update could not be processed for unknown database error".format(
                lab_id
            )
        )

        raise VliError(
            message="Virtual lab could not be saved to the database",
            error_code=VliErrorCode.OTHER,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except Exception as error:
        logger.error(
            "Virtual lab could not be saved due to an unknown error {}".format(error)
        )

        raise VliError(
            message="Virtual lab could not be saved to the database",
            error_code=VliErrorCode.OTHER,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
