from http import HTTPStatus
from uuid import UUID

from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.core.exceptions.generic_exceptions import UserNotInList
from virtual_labs.domain.labs import AddUserToVirtualLab
from virtual_labs.infrastructure.email.email_service import EmailDetails, send_invite
from virtual_labs.repositories import labs as lab_repo
from virtual_labs.repositories.invite_repo import InviteMutationRepository
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.usecases.labs.lab_authorization import is_user_admin_of_lab


async def invite_user_to_lab(
    lab_id: UUID4, inviter_id: UUID4, invite_details: AddUserToVirtualLab, db: Session
) -> UUID4:
    user_repo = UserQueryRepository()
    invite_repo = InviteMutationRepository(db)

    try:
        lab = lab_repo.get_virtual_lab(db, lab_id)
        if not is_user_admin_of_lab(user_id=inviter_id, lab=lab):
            raise UserNotInList(
                f"Only admins of lab can invite other users and user {inviter_id} is not admin of lab {lab.name}"
            )
        user_to_invite = user_repo.retrieve_user_by_email(invite_details.email)
        user_id = UUID(user_to_invite.id) if user_to_invite is not None else None

        invite = invite_repo.add_lab_invite(
            virtual_lab_id=lab_id,
            # Inviter details
            inviter_id=inviter_id,
            # Invitee details
            invitee_id=user_id,
            invitee_role=invite_details.role,
            invitee_email=invite_details.email,
        )

        await send_invite(
            details=EmailDetails(
                recipient=invite_details.email,
                invite_id=UUID(str(invite.id)),
                lab_id=lab_id,
                lab_name=str(lab.name),
            )
        )
        return UUID(str(invite.id))
    except EmailError as error:
        logger.error(f"Error when sending email invite {error.message} {error.detail}")
        invite_repo.delete_invite(invite_id=UUID(str(invite.id)))
        raise VliError(
            message=f"There was an error while emailing virtual lab the invite to user {invite_details.email}. Please try sending the invite again.",
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    except UserNotInList:
        raise VliError(
            message=f"Only admins of lab can invite other users and user {inviter_id} is not admin of lab {lab.name}",
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.FORBIDDEN,
        )
    except ValueError as error:
        logger.error(f"ValueError when inviting user {invite_details.email} {error}")
        raise VliError(
            message=str(error),
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    except SQLAlchemyError as error:
        logger.error(f"Db error when inviting user {invite_details.email}: {error}")
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
