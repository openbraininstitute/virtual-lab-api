from http import HTTPStatus
from uuid import UUID

from fastapi import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.invite import InvitePayload
from virtual_labs.repositories.invite_repo import (
    InviteMutationRepository,
    InviteQueryRepository,
)


async def cancel_project_invite(
    session: AsyncSession, project_id: UUID4, payload: InvitePayload
) -> Response:
    try:
        iqr = InviteQueryRepository(session)
        imr = InviteMutationRepository(session)

        invite = await iqr.get_project_invite_by_params(
            project_id=project_id,
            email=str(payload.email),
            role=payload.role,
        )

        if invite is not None and not invite.accepted:
            await imr.delete_project_invite(UUID(str(invite.id)))
            return VliResponse.new(
                message=f"Invite for email {payload.email} successfully deleted.",
                data=None,
            )

        raise VliError(
            message=f"No invite found for user {payload.email} for lab {project_id}",
            http_status_code=HTTPStatus.NOT_FOUND,
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
        )
    except VliError as error:
        raise error
    except SQLAlchemyError as error:
        logger.error(
            f"Invite for project {project_id} user {payload.email} could not be deleted due to database error {error}"
        )
        raise VliError(
            message=f"Invite for project {project_id} user {payload.email} could not be deleted due to a database error.",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=VliErrorCode.DATABASE_ERROR,
        )
    except Exception as error:
        logger.exception(
            f"Invite for project {project_id} user {payload.email} could not be deleted due to an unknown error {error}"
        )
        raise VliError(
            message=f"Invite for project {project_id} user {payload.email} could not be deleted due to an unknown error.",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=VliErrorCode.SERVER_ERROR,
        )
