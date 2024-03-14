from http import HTTPStatus

from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import VirtualLabDomainVerbose
from virtual_labs.repositories import labs as repository
from virtual_labs.usecases.labs.lab_with_not_deleted_projects import (
    lab_with_not_deleted_projects,
)


def get_virtual_lab(db: Session, lab_id: UUID4) -> VirtualLabDomainVerbose:
    try:
        db_lab = repository.get_virtual_lab(db, lab_id)
        return lab_with_not_deleted_projects(db_lab)

    except SQLAlchemyError:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
