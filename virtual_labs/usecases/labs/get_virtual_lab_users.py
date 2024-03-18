from http import HTTPStatus

from loguru import logger
from pydantic import UUID4, EmailStr
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import VirtualLabUsers
from virtual_labs.domain.user import ShortenedUser
from virtual_labs.infrastructure.kc.models import UserRepresentation
from virtual_labs.repositories import labs as lab_repository
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.invite_repo import InviteQueryRepository
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.usecases.labs.lab_authorization import is_user_in_lab


# TODO: !36 If we create a temporary User in KC for unregistered users then this function will not be needed
def get_pending_user(
    user: UserRepresentation | None, user_email: EmailStr
) -> UserRepresentation:
    """Creates a dummy UserRepresentation object if user is not yet registered on KeyCloak"""
    if user is None:
        return UserRepresentation(
            id="unknown",
            username=user_email,
            emailVerified=False,
            createdTimestamp=0,
            enabled=False,
            totp=False,
            disableableCredentialTypes=[],
            requiredActions=[],
            notBefore=0,
        )
    return user


def get_virtual_lab_users(
    db: Session, lab_id: UUID4, user_id: UUID4
) -> VirtualLabUsers:
    invite_repo = InviteQueryRepository(db)
    group_repo = GroupQueryRepository()
    user_repo = UserQueryRepository()

    try:
        lab = lab_repository.get_virtual_lab(db, lab_id)
        if not is_user_in_lab(user_id, lab):
            raise VliError(
                message=f"User {user_id} is not member of lab {lab.name} and therefore cannot retrieve lab users",
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=HTTPStatus.FORBIDDEN,
            )
        admins = [
            ShortenedUser.model_validate(admin)
            for admin in group_repo.retrieve_group_users(str(lab.admin_group_id))
        ]
        members = [
            ShortenedUser.model_validate(member)
            for member in group_repo.retrieve_group_users(str(lab.member_group_id))
        ]
        pending_users = [
            ShortenedUser.model_validate(
                get_pending_user(
                    user=(user_repo.retrieve_user_by_email(str(invite.user_email))),
                    user_email=str(invite.user_email),
                )
            )
            for invite in invite_repo.get_pending_users_for_lab(lab_id)
        ]
        return VirtualLabUsers(
            added_users=admins + members, pending_users=pending_users
        )
    except NoResultFound:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    except ValueError:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Could not retrieve users from keycloak",
        )
    except SQLAlchemyError as error:
        logger.error(
            f"Virtual lab {lab_id} could not be retrieved due to an unknown database error: {error}"
        )

        raise VliError(
            message="Virtual lab could not be retrieved from the database",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except Exception as error:
        logger.error(f"Users could not be retrieved due to an unknown error {error}")

        raise VliError(
            message="Users could not be retrieved due to an unknown error",
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
