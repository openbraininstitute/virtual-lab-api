from http import HTTPStatus

from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import VirtualLab, VirtualLabResponse
from virtual_labs.repositories import labs as repository
from virtual_labs.repositories.group_repo import GroupQueryRepository


async def get_virtual_lab(
    db: AsyncSession, lab_id: UUID4, user_id: UUID4
) -> VirtualLabResponse:
    gqr = GroupQueryRepository()
    try:
        db_lab = await repository.get_undeleted_virtual_lab(db, lab_id)
        admins = await gqr.a_retrieve_group_users(group_id=db_lab.admin_group_id)
        return VirtualLabResponse(
            virtual_lab=VirtualLab.model_validate(db_lab),
            admins=[UUID4(a.id) for a in admins],
        )
    except SQLAlchemyError as error:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        ) from error
    except VliError as error:
        raise error
