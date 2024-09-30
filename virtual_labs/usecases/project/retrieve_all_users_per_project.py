from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.user import UserWithInviteStatus
from virtual_labs.infrastructure.db.models import Project
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.invite_repo import InviteQueryRepository
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.usecases.labs.get_virtual_lab_users import get_pending_user


async def retrieve_all_users_per_project_use_case(
    session: AsyncSession,
    project: Project,
) -> Response:
    gqr = GroupQueryRepository()
    invite_repo = InviteQueryRepository(session)
    user_repo = UserQueryRepository()

    try:
        admins = [
            UserWithInviteStatus(
                **admin.model_dump(),
                invite_accepted=True,
                role=UserRoleEnum.admin,
            )
            for admin in (await gqr.retrieve_group_users(str(project.admin_group_id)))
        ]
        members = [
            UserWithInviteStatus(
                **member.model_dump(),
                invite_accepted=True,
                role=UserRoleEnum.member,
            )
            for member in (await gqr.retrieve_group_users(str(project.member_group_id)))
        ]
        pending_invites = await invite_repo.get_pending_users_for_project(project.uuid)
        pending_users = [
            UserWithInviteStatus(
                **get_pending_user(
                    user=(
                        await user_repo.retrieve_user_by_email(str(invite.user_email))
                    ),
                    user_email=str(invite.user_email),
                ).model_dump(),
                invite_accepted=False,
                role=(
                    UserRoleEnum.admin
                    if str(invite.role) == UserRoleEnum.admin.value
                    else UserRoleEnum.member
                ),
            )
            for invite in pending_invites
        ]
        users = admins + members + pending_users
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving users for a project failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during retrieving users per project: {project.uuid} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving users per project",
        )
    else:
        return VliResponse.new(
            message="Users found successfully",
            data={"users": users, "total": len(users)},
        )
