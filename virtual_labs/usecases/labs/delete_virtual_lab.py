from http import HTTPStatus

from loguru import logger
from pydantic import UUID4, BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from virtual_labs.usecases.labs.lab_authorization import is_user_admin_of_lab


class ProjectWithIds(BaseModel):
    id: UUID4
    deleted: bool
    admin_group_id: str
    member_group_id: str

    class Config:
        from_attributes = True


def delete_virtual_lab(db: Session, lab_id: UUID4, user_id: UUID4) -> models.VirtualLab:
    try:
        lab = repository.get_virtual_lab(db, lab_id)
        if not is_user_admin_of_lab(user_id, lab):
            raise VliError(
                message=f"Only admins of virtual lab {lab.name} are authorized to delete virtual lab.",
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=HTTPStatus.FORBIDDEN,
            )
        return repository.delete_virtual_lab(db, lab_id)
    except SQLAlchemyError:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    except VliError as error:
        raise error
    except Exception as error:
        logger.warning(f"Deleting virtual lab groups failed  failed: {error}")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message=f"Virtual lab deletion could not be completed due to a keycloak error: {error}",
        )
