from http import HTTPStatus
from typing import Tuple
from uuid import UUID

from fastapi import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.project import ProjectInviteIn, ProjectInviteOut
from virtual_labs.infrastructure.email.email_service import EmailDetails, send_invite
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.invite_repo import (
    InviteMutationRepository,
    InviteQueryRepository,
)
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.shared.utils.is_user_in_project import is_user_in_project


async def invite_user_to_project(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    invite_details: ProjectInviteIn,
    auth: Tuple[AuthUser, str],
) -> Response:
    pr = ProjectQueryRepository(session)
    user_repo = UserQueryRepository()
    invite_repo = InviteMutationRepository(session)
    invite_query_repo = InviteQueryRepository(session)
    inviter_id = get_user_id_from_auth(auth)
    user, _ = auth

    try:
        project, lab = await pr.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id, project_id=project_id
        )

        invite = await invite_query_repo.get_project_invite_by_params(
            project_id=project_id,
            email=invite_details.email,
            role=invite_details.role,
        )
        if user.email == invite_details.email:
            raise ValueError("Self invite is forbidden")

        user_to_invite = user_repo.retrieve_user_by_email(invite_details.email)
        user_id = UUID(user_to_invite.id) if user_to_invite is not None else None

        inviter = await user_repo.retrieve_user_from_kc(str(inviter_id))
        # If user is already in project, raise an error
        if user_id is not None and (await is_user_in_project(user_id, project)):
            logger.error(
                f"User with email {invite_details.email} is already in project {project.name}"
            )
            raise VliError(
                message=f"User with email {invite_details.email} is already in project {project.name}",
                http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            )

        if invite is None:
            invite = await invite_repo.add_project_invite(
                project_id=project_id,
                inviter_id=inviter_id,
                invitee_id=user_id,
                invitee_role=invite_details.role,
                invitee_email=invite_details.email,
            )
            await session.refresh(project)
            await session.refresh(lab)
            await send_invite(
                details=EmailDetails(
                    recipient=invite_details.email,
                    invitee_name=(
                        None
                        if user_to_invite is None
                        else f"{user_to_invite.firstName} {user_to_invite.lastName}"
                    ),
                    inviter_name=f"{inviter.firstName} {inviter.lastName}",
                    invite_id=UUID(str(invite.id)),
                    lab_id=virtual_lab_id,
                    lab_name=str(lab.name),
                    project_id=project_id,
                    project_name=str(project.name),
                )
            )
        else:
            await invite_repo.update_project_invite(
                invite_id=UUID(str(invite.id)),
                properties={"updated_at": func.now()},
            )
            await session.refresh(invite)
            await session.refresh(project)
            await session.refresh(lab)
            await send_invite(
                details=EmailDetails(
                    recipient=invite_details.email,
                    invitee_name=(
                        None
                        if user_to_invite is None
                        else f"{user_to_invite.firstName} {user_to_invite.lastName}"
                    ),
                    inviter_name=f"{inviter.firstName} {inviter.lastName}",
                    invite_id=UUID(str(invite.id)),
                    lab_id=virtual_lab_id,
                    lab_name=str(lab.name),
                    project_id=project_id,
                    project_name=str(project.name),
                )
            )
        return VliResponse.new(
            message="User invited successfully",
            data=ProjectInviteOut(invite_id=UUID(str(invite.id))),
        )
    except EmailError as error:
        logger.error(f"Error when sending email invite {error.message} {error.detail}")
        if invite:
            await invite_repo.delete_project_invite(invite_id=UUID(str(invite.id)))
        raise VliError(
            message=f"There was an error while emailing the project invite to user {invite_details.email}. Please try sending the invite again.",
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    except ValueError as error:
        logger.error(f"ValueError when inviting user {invite_details.email} {error}")
        raise VliError(
            message=str(error),
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except SQLAlchemyError as error:
        logger.error(
            f"Db error when inviting user to project {invite_details.email}: {error}"
        )
        raise VliError(
            message=f"Invite to user could not be sent due to an error in database. {error}",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    except VliError as error:
        raise error
    except Exception as error:
        logger.error(
            f"Invite could not be sent to user due to an unknown error {error}"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Unknown error when sending invite to user",
        )
