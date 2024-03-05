from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from sqlalchemy.orm import Session
from virtual_labs.core.exceptions.api_error import VlmError, VlmErrorCode
from sqlalchemy.exc import SQLAlchemyError
from http import HTTPStatus


def create_virtual_lab(db: Session, lab: domain.VirtualLabCreate) -> models.VirtualLab:
    try:
        return repository.create_virtual_lab(db, lab)
    except SQLAlchemyError:
        raise VlmError(
            message="A virtual lab with this name already exists",
            error_code=VlmErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
