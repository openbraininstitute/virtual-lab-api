from http import HTTPStatus

from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import UserNotInList
from virtual_labs.domain.labs import VirtualLabDomainVerbose
from virtual_labs.repositories import labs as repository
from virtual_labs.usecases.labs.lab_authorization import is_user_in_lab
from virtual_labs.usecases.labs.lab_with_not_deleted_projects import (
    lab_with_not_deleted_projects,
)


async def get_virtual_lab(
    db: AsyncSession, lab_id: UUID4, user_id: UUID4
) -> VirtualLabDomainVerbose:
    try:
        db_lab = await repository.get_undeleted_virtual_lab(db, lab_id)
        if is_user_in_lab(user_id=user_id, lab=db_lab):
            return lab_with_not_deleted_projects(db_lab, user_id)
        raise UserNotInList(
            f"User {user_id} does not have read permissions for virtual lab {lab_id}"
        )
    except UserNotInList:
        raise VliError(
            message=f"User {user_id} does not have read permissions for virtual lab {lab_id}",
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.FORBIDDEN,
        )
    except SQLAlchemyError as error:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        ) from error
    except VliError as error:
        raise error
