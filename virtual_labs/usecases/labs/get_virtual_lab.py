from pydantic import UUID4
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from sqlalchemy.orm import Session
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from sqlalchemy.exc import SQLAlchemyError
from http import HTTPStatus


def get_virtual_lab(db: Session, lab_id: UUID4) -> models.VirtualLab:
    try:
        return repository.get_virtual_lab(db, lab_id)
    except SQLAlchemyError:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
