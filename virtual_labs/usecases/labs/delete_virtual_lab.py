from http import HTTPStatus

from loguru import logger
from pydantic import UUID4, BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import UserNotInList
from virtual_labs.external.nexus.deprecate_organization import (
    deprecate_nexus_organization,
)
from virtual_labs.infrastructure.db import models
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories import labs as repository
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.usecases.labs.lab_authorization import is_user_admin_of_lab


class ProjectWithIds(BaseModel):
    id: UUID4
    deleted: bool
    admin_group_id: str
    member_group_id: str

    class Config:
        from_attributes = True


async def delete_virtual_lab(
    db: Session, lab_id: UUID4, auth: tuple[AuthUser, str]
) -> models.VirtualLab:
    try:
        lab = repository.get_virtual_lab(db, lab_id)
        if not is_user_admin_of_lab(user_id=get_user_id_from_auth(auth), lab=lab):
            raise UserNotInList(
                f"Only admins of virtual lab {lab.name} are authorized to delete virtual lab."
            )
        nexus_org = await deprecate_nexus_organization(lab_id, auth)
        logger.debug(f"Deprecated nexus organization {nexus_org.label}")
        return repository.delete_virtual_lab(db, lab_id)
    except UserNotInList:
        raise VliError(
            message=f"Only admins of virtual lab {lab.name} are authorized to delete virtual lab.",
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.FORBIDDEN,
        )
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
