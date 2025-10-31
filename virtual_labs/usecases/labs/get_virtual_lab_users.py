import asyncio
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from pydantic import UUID4, EmailStr
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.labs import VirtualLabUsers
from virtual_labs.domain.user import UserWithInviteStatus
from virtual_labs.infrastructure.kc.models import (
    UserNotInKCRepresentation,
    UserRepresentation,
)
from virtual_labs.repositories import labs as lab_repository
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.invite_repo import InviteQueryRepository
from virtual_labs.repositories.user_repo import UserQueryRepository


def get_pending_user(
    user: UserRepresentation | None, user_email: EmailStr
) -> UserRepresentation | UserNotInKCRepresentation:
    """Creates a dummy UserRepresentation object if user is not yet registered on KeyCloak"""
    if user is None:
        return UserNotInKCRepresentation(
            id=None,
            firstName="unknown",
            lastName="unknown",
            username=user_email,
            email=user_email,
            emailVerified=False,
            createdTimestamp=0,
            enabled=False,
            totp=False,
            disableableCredentialTypes=[],
            requiredActions=[],
            notBefore=0,
        )
    return user


async def get_virtual_lab_users(
    db: AsyncSession,
    lab_id: UUID4,
) -> VirtualLabUsers:
    invite_repo = InviteQueryRepository(db)
    group_repo = GroupQueryRepository()
    user_repo = UserQueryRepository()

    try:
        lab = await lab_repository.get_undeleted_virtual_lab(db, lab_id)

        admin_users_task = group_repo.a_retrieve_group_users(str(lab.admin_group_id))
        member_users_task = group_repo.a_retrieve_group_users(str(lab.member_group_id))

        admin_users_raw, member_users_raw = await asyncio.gather(
            admin_users_task, member_users_task
        )

        user_roles = {}

        for admin in admin_users_raw:
            user_roles[admin.id] = UserWithInviteStatus(
                **admin.model_dump(),
                invite_accepted=True,
                role=UserRoleEnum.admin,
            )

        # NOTE: Only comment for the moment, it may be need later
        # to return back the members
        # currently virtual lab should only add admins through the UI

        # for member in member_users_raw:
        #     if member.id not in user_roles:
        #         user_roles[member.id] = UserWithInviteStatus(
        #             **member.model_dump(),
        #             invite_accepted=True,
        #             role=UserRoleEnum.member,
        #         )

        invites = await invite_repo.get_pending_users_for_lab(lab_id)
        pending_users = [
            UserWithInviteStatus(
                **get_pending_user(
                    user=(user_repo.retrieve_user_by_email(str(invite.user_email))),
                    user_email=str(invite.user_email),
                ).model_dump(),
                invite_accepted=False,
                role=UserRoleEnum.admin
                if str(invite.role) == UserRoleEnum.admin.value
                else UserRoleEnum.member,
            )
            for invite in invites
        ]

        active_users = list(user_roles.values())
        users = active_users + pending_users
        return VirtualLabUsers(
            owner_id=UUID(str(lab.owner_id)),
            users=users,
            total_active=len(active_users),
            total=len(users),
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
        ) from error
