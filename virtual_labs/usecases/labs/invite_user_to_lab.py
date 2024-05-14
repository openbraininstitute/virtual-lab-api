from http import HTTPStatus
from uuid import UUID

from loguru import logger
from pydantic import UUID4, EmailStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.domain.invite import AddUser
from virtual_labs.infrastructure.email.email_service import EmailDetails, send_invite
from virtual_labs.repositories import labs as lab_repo
from virtual_labs.repositories.invite_repo import (
    InviteMutationRepository,
    InviteQueryRepository,
)
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.shared.utils.is_user_in_lab import is_user_in_lab


async def send_email_to_user_or_rollback(
    invite_id: UUID,
    invitee_name: str | None,
    inviter_name: str,
    email: EmailStr,
    lab_name: str,
    lab_id: UUID,
    invite_repo: InviteMutationRepository,
) -> None:
    try:
        await send_invite(
            details=EmailDetails(
                recipient=email,
                invite_id=invite_id,
                lab_id=lab_id,
                lab_name=lab_name,
                invitee_name=invitee_name,
                inviter_name=inviter_name,
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


async def invite_user_to_lab(
    lab_id: UUID4,
    inviter_id: UUID4,
    invite_details: AddUser,
    db: AsyncSession,
) -> UUID4:
    user_repo = UserQueryRepository()
    invite_query_repo = InviteQueryRepository(db)
    invite_mutation_repo = InviteMutationRepository(db)

    try:
        lab = await lab_repo.get_undeleted_virtual_lab(db, lab_id)

        user_to_invite = user_repo.retrieve_user_by_email(invite_details.email)
        inviting_user = user_repo.retrieve_user_from_kc(str(inviter_id))
        user_id = UUID(user_to_invite.id) if user_to_invite is not None else None
        invitee_name = (
            None
            if user_to_invite is None
            else f"{user_to_invite.firstName} {user_to_invite.lastName}"
        )

        # If user is already in lab, raise an error
        if user_id is not None and (is_user_in_lab(user_id, lab)):
            logger.error(
                f"User with email {invite_details.email} is already in lab {lab.name}"
            )
            raise VliError(
                message=f"User with email {invite_details.email} is already in lab {lab.name}",
                http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            )

        existing_invite = await invite_query_repo.get_lab_invite_by_params(
            lab_id=UUID(str(lab.id)),
            email=invite_details.email,
            role=invite_details.role,
        )

        if existing_invite is None:
            invite = await invite_mutation_repo.add_lab_invite(
                virtual_lab_id=lab_id,
                # Inviter details
                inviter_id=inviter_id,
                # Invitee details
                invitee_id=user_id,
                invitee_role=invite_details.role,
                invitee_email=invite_details.email,
            )
            # Need to refresh the lab because the invite is commited inside the repo.
            await db.refresh(lab)
            await send_email_to_user_or_rollback(
                invite_id=UUID(str(invite.id)),
                invitee_name=invitee_name,
                inviter_name=f"{inviting_user.firstName} {inviting_user.lastName}",
                email=invite_details.email,
                lab_name=str(lab.name),
                lab_id=UUID(str(lab.id)),
                invite_repo=invite_mutation_repo,
            )
            return UUID(str(invite.id))
        else:
            logger.debug(
                f"Invite {existing_invite.id} for user already exists. Updating the invite and sending refreshed link"
            )
            await invite_mutation_repo.update_lab_invite(UUID(str(existing_invite.id)))
            # Need to refresh the lab because the invite is commited inside the repo.
            await db.refresh(lab)
            await db.refresh(existing_invite)

            await send_email_to_user_or_rollback(
                invite_id=UUID(str(existing_invite.id)),
                invitee_name=invitee_name,
                inviter_name=f"{inviting_user.firstName} {inviting_user.lastName}",
                email=invite_details.email,
                lab_name=str(lab.name),
                lab_id=UUID(str(lab.id)),
                invite_repo=invite_mutation_repo,
            )
            return UUID(str(existing_invite.id))
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
