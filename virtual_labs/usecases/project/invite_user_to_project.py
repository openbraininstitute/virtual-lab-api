from http import HTTPStatus
from uuid import UUID

from fastapi import Response
from loguru import logger
from pydantic import UUID4, EmailStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.core.exceptions.generic_exceptions import ForbiddenOperation
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.invite import InvitePayload
from virtual_labs.domain.labs import InvitationResponse
from virtual_labs.infrastructure.email.invite_email import EmailDetails, send_invite
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.invite_repo import (
    InviteMutationRepository,
    InviteQueryRepository,
)
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import UserQueryRepository


async def send_email_to_user_or_rollback(
    invite_id: UUID,
    inviter_name: str,
    email: EmailStr,
    lab_name: str,
    lab_id: UUID,
    project_name: str,
    project_id: UUID,
    invite_repo: InviteMutationRepository,
) -> None:
    try:
        await send_invite(
            payload=EmailDetails(
                recipient=email,
                invite_id=invite_id,
                lab_id=lab_id,
                lab_name=lab_name,
                inviter_name=inviter_name,
                project_name=project_name,
                project_id=project_id,
            )
        )
    except EmailError as error:
        logger.error(
            f"Error when sending email invite to user {email} {error.message} {error.detail}"
        )
        await invite_repo.delete_lab_invite(invite_id=UUID(str(invite_id)))
        raise VliError(
            message=f"There was an error while emailing virtual lab invite to {email}. Please try sending the invite again.",
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


async def invite_user_to_project(
    session: AsyncSession,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    inviter_id: UUID4,
    invite_details: InvitePayload,
) -> Response:
    imr = InviteMutationRepository(session)
    prq = ProjectQueryRepository(session)
    iqr = InviteQueryRepository(session)
    ur = UserQueryRepository()
    gqr = GroupQueryRepository()

    try:
        project, virtual_lab = await prq.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
        )

        virtual_lab_admins = await gqr.a_retrieve_group_user_ids(
            group_id=virtual_lab.admin_group_id,
        )

        # allow the project admins to invite members
        if (
            inviter_id not in virtual_lab_admins
            and invite_details.role == UserRoleEnum.admin.value
        ):
            raise ForbiddenOperation("Project admins can only invite members")

        inviting_user = ur.retrieve_user_from_kc(str(inviter_id))
        invite = await iqr.get_project_invite_by_params(
            project_id=UUID(str(project_id)),
            email=invite_details.email,
            role=invite_details.role,
        )

        if invite is None:
            invite = await imr.add_project_invite(
                project_id=project_id,
                inviter_id=inviter_id,
                invitee_role=invite_details.role,
                invitee_email=invite_details.email,
            )

        else:
            logger.debug(
                f"Invite {invite.id} for user already exists. Updating the invite and sending refreshed link"
            )
            await imr.update_project_invite(
                invite_id=invite.id,
                properties={
                    "accepted": False,
                },
            )

        await session.refresh(virtual_lab)
        await session.refresh(project)
        await session.refresh(invite)

        await send_email_to_user_or_rollback(
            invite_id=UUID(str(invite.id)),
            inviter_name=f"{inviting_user.firstName} {inviting_user.lastName}",
            email=invite_details.email,
            lab_name=virtual_lab.name,
            lab_id=virtual_lab.id,
            project_id=project_id,
            project_name=project.name,
            invite_repo=imr,
        )
        return VliResponse.new(
            message="Invite sent successfully",
            data=InvitationResponse(id=invite.id),
        )
    except ForbiddenOperation as e:
        logger.error(
            f"ForbiddenOperation when inviting user {invite_details.email} {e}"
        )
        raise VliError(
            message="User is not allowed to invite users to this project",
            error_code=VliErrorCode.FORBIDDEN_OPERATION,
            http_status_code=HTTPStatus.FORBIDDEN,
        ) from e
    except ValueError as error:
        logger.error(f"ValueError when inviting user {invite_details.email} {error}")
        raise VliError(
            message=str(error),
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    except SQLAlchemyError as error:
        logger.exception(error)
        logger.error(f"Db error when inviting user {invite_details.email}: {error}")
        raise VliError(
            message=f"Invite to user could not be sent due to an error in database. {error}",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from error
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
        ) from error
