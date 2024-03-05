from pydantic import UUID4
from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from sqlalchemy.orm import Session
from virtual_labs.core.exceptions.api_error import VlmError, VlmErrorCode
from sqlalchemy.exc import SQLAlchemyError
from http import HTTPStatus


def update_virtual_lab(
    db: Session, lab_id: UUID4, lab: domain.VirtualLabUpdate
) -> models.VirtualLab:
    try:
        return repository.update_virtual_lab(db, lab_id, lab)
    except SQLAlchemyError:
        raise VlmError(
            message="Virtual lab not found",
            error_code=VlmErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
