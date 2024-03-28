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
from virtual_labs.repositories.invite_repo import InviteMutationRepository
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories import labs as lab_repo
from virtual_labs.repositories.invite_repo import (
    InviteMutationRepository,
    InviteQueryRepository,
)
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def invite_user_to_project(
    session: Session,
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    invite_details: ProjectInviteIn,
    session: AsyncSession,
) -> VliAppResponse[ProjectInviteOut]:
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    pr = ProjectQueryRepository(session)
    user_repo = UserQueryRepository()
    invite_repo = InviteMutationRepository(session)
    invite_query_repo = InviteQueryRepository(session)
    inviter_id = get_user_id_from_auth(auth)

    try:
        project, _ = pr.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id, project_id=project_id
        )
        lab = lab_repo.get_virtual_lab(session, virtual_lab_id)

        invite = invite_query_repo.get_project_invite_by_params(
            project_id=project_id,
            email=invite_details.email,
            role=invite_details.role,
        )
        lab = lab_repo.get_virtual_lab(session, lab_id)

        if invite is None:
            user_to_invite = user_repo.retrieve_user_by_email(invite_details.email)
            user_id = UUID(user_to_invite.id) if user_to_invite is not None else None

            invite = invite_repo.add_project_invite(
                project_id=project_id,
                inviter_id=inviter_id,
                invitee_id=user_id,
                invitee_role=invite_details.role,
                invitee_email=invite_details.email,
            )

            await send_invite(
                details=EmailDetails(
                    recipient=invite_details.email,
                    invite_id=UUID(str(invite.id)),
                    lab_id=virtual_lab_id,
                    lab_name=str(lab.name),
                    project_id=project_id,
                    project_name=str(project.name),
                )
            )
        else:
            invite_repo.update_project_invite(
                invite_id=UUID(str(invite.id)),
                properties={"updated_at": func.now()},
            )
            await send_invite(
                details=EmailDetails(
                    recipient=invite_details.email,
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
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
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
