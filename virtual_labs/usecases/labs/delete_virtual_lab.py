from http import HTTPStatus

from loguru import logger
from pydantic import UUID4, BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from virtual_labs.repositories.group_repo import GroupMutationRepository


class ProjectWithIds(BaseModel):
    id: UUID4
    deleted: bool
    admin_group_id: str
    member_group_id: str

    class Config:
        from_attributes = True


def delete_virtual_lab(db: Session, lab_id: UUID4) -> models.VirtualLab:
    try:
        lab = repository.get_virtual_lab(db, lab_id)
        group_repo = GroupMutationRepository()

        # Delete groups for lab
        group_repo.delete_group(group_id=str(lab.admin_group_id))
        group_repo.delete_group(group_id=str(lab.member_group_id))

        # Delete groups for un-deleted children projects also
        for db_project in lab.projects:
            project = ProjectWithIds.model_validate(db_project)
            if not project.deleted:
                group_repo.delete_group(group_id=project.admin_group_id)
                group_repo.delete_group(group_id=project.member_group_id)

        # Now mark db row as deleted
        repository.delete_virtual_lab(db, lab_id)
        return lab
    except SQLAlchemyError:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    except Exception as error:
        logger.warning(f"Deleting virtual lab groups failed  failed: {error}")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message=f"Virtual lab deletion could not be completed due to a keycloak error: {error}",
        )
