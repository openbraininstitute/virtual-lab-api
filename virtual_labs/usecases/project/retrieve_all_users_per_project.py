from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.user import UserWithInviteStatus
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository


async def retrieve_all_users_per_project_use_case(
    session: AsyncSession,
    virtual_lab_id: UUID4,
    project_id: UUID4,
) -> Response:
    gqr = GroupQueryRepository()
    pqr = ProjectQueryRepository(session)

    try:
        project, _ = await pqr.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id, project_id=project_id
        )
    except Exception:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving project failed",
        )

    try:
        admins = [
            UserWithInviteStatus(
                **admin.model_dump(),
                invite_accepted=True,
                role=UserRoleEnum.admin,
            )
            for admin in gqr.retrieve_group_users(str(project.admin_group_id))
        ]
        members = [
            UserWithInviteStatus(
                **member.model_dump(),
                invite_accepted=True,
                role=UserRoleEnum.member,
            )
            for member in gqr.retrieve_group_users(str(project.member_group_id))
        ]

        active_users = admins + members
        owner_id = project.owner_id
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving users for a project failed",
        )
    except Exception as ex:
        logger.error(f"Error during retrieving users per project: {project_id} ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving users per project",
        )
    else:
        return VliResponse.new(
            message="Users found successfully",
            data={
                "owner_id": owner_id,
                "users": active_users,
                "total_active": len(active_users),
                "total": len(active_users),
            },
        )
