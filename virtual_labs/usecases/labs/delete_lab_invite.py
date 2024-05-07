from http import HTTPStatus
from uuid import UUID

from loguru import logger
from pydantic import UUID4, EmailStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.labs import LabResponse
from virtual_labs.repositories.invite_repo import (
    InviteMutationRepository,
    InviteQueryRepository,
)


async def delete_lab_invite(
    db: AsyncSession,
    lab_id: UUID4,
    email: EmailStr,
    role: UserRoleEnum = UserRoleEnum.member,
) -> LabResponse[None]:
    try:
        invite_query_repo = InviteQueryRepository(db)
        invite_mut_repo = InviteMutationRepository(db)

        invite = await invite_query_repo.get_lab_invite_by_params(
            lab_id, str(email), role
        )
        if invite is None:
            raise VliError(
                message=f"No invite found for user {email} for lab {lab_id}",
                http_status_code=HTTPStatus.NOT_FOUND,
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
            )

        if invite.accepted is True:
            raise VliError(
                message=f"Invite is already accepted by user {email} and can therefore not be deleted",
                http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                error_code=VliErrorCode.ENTITY_ALREADY_UPDATED,
            )

        await invite_mut_repo.delete_lab_invite(UUID(str(invite.id)))
        return LabResponse(
            message=f"Invite for email {email} successfully deleted.", data=None
        )
    except VliError as error:
        raise error
    except SQLAlchemyError as error:
        logger.error(
            f"Invite for lab {lab_id} user {email} could not be deleted due to database error {error}"
        )
        raise VliError(
            message=f"Invite for lab {lab_id} user {email} could not be deleted due to a database error.",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=VliErrorCode.DATABASE_ERROR,
        )
    except Exception as error:
        logger.exception(
            f"Invite for lab {lab_id} user {email} could not be deleted due to an unknown error {error}"
        )
        raise VliError(
            message=f"Invite for lab {lab_id} user {email} could not be deleted due to an unknown error.",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=VliErrorCode.SERVER_ERROR,
        )
