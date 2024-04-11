from http import HTTPStatus

from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import LabByIdOut, VirtualLabWithUsers
from virtual_labs.repositories import labs as repository
from virtual_labs.usecases.labs.get_virtual_lab_users import get_virtual_lab_users
from virtual_labs.usecases.labs.lab_with_not_deleted_projects import (
    lab_with_not_deleted_projects,
)


async def get_virtual_lab(
    db: AsyncSession, lab_id: UUID4, user_id: UUID4
) -> LabByIdOut:
    try:
        db_lab = await repository.get_undeleted_virtual_lab(db, lab_id)
        lab = lab_with_not_deleted_projects(db_lab, user_id)
        users = (await get_virtual_lab_users(db, lab_id)).users
        lab_with_users = VirtualLabWithUsers.model_validate(
            lab.model_copy(update={"users": users})
        )
        return LabByIdOut(virtual_lab=lab_with_users)
    except SQLAlchemyError as error:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        ) from error
    except VliError as error:
        raise error
