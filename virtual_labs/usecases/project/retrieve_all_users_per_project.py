from http import HTTPStatus as status
from typing import List

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.user import ShortenedUser
from virtual_labs.infrastructure.kc.models import UserRepresentation
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository


async def retrieve_all_users_per_project_use_case(
    session: Session,
    virtual_lab_id: UUID4,
    project_id: UUID4,
) -> Response | VliError:
    gqr = GroupQueryRepository()
    pqr = ProjectQueryRepository(session)

    try:
        project, _ = pqr.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id, project_id=project_id
        )
    except Exception:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving project failed",
        )

    try:
        members = gqr.retrieve_group_users(str(project.member_group_id))
        admins = gqr.retrieve_group_users(str(project.admin_group_id))
        users: List[UserRepresentation] = list(
            {v.id: v for v in admins + members}.values()
        )

        shortened_users = [ShortenedUser(**u.__dict__) for u in users]
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
            data={"users": shortened_users, "total": len(users)},
        )
