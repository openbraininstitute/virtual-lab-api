from http import HTTPStatus

from loguru import logger
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.usecases.plans.verify_plan import verify_plan


def create_virtual_lab(db: Session, lab: domain.VirtualLabCreate) -> models.VirtualLab:
    try:
        verify_plan(db, lab.plan_id)
        return repository.create_virtual_lab(db, lab)
    except IntegrityError as error:
        logger.error(
            "Virtual lab could not be created due to database error {}".format(error)
        )
        raise VliError(
            message="Another virtual lab with same name already exists",
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
        )
    except ValueError as error:
        raise VliError(
            message=str(error),
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except SQLAlchemyError as error:
        logger.error(
            "Virtual lab could not be created due to an unknown database error {}".format(
                type(error)
            )
        )

        raise VliError(
            message="Virtual lab could not be saved to the database",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except Exception as error:
        logger.error(
            "Virtual lab could not be created due to an unknown error {}".format(error)
        )

        raise VliError(
            message="Virtual lab could not be created",
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
