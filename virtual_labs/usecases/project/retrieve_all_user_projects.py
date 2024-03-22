from http import HTTPStatus as status
from typing import Tuple

from fastapi.responses import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.project import Project, VirtualLabModel
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository


async def retrieve_all_user_projects_use_case(
    session: Session,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    pr = ProjectQueryRepository(session)
    gqr = GroupQueryRepository()
    user, _ = auth
    user_id = user.sub

    try:
        groups = gqr.retrieve_user_groups(user_id=user_id)
        group_ids = [g.id for g in groups]

        projects_vl_tuple = pr.retrieve_projects_batch(groups=group_ids)

        projects = [
            {
                **Project(**p.__dict__).model_dump(),
                "virtual_lab": VirtualLabModel(**v.__dict__),
            }
            for p, v in projects_vl_tuple
        ]
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving projects failed",
        )
    except Exception as ex:
        print("ec", ex)
        logger.error(f"Error during retrieving project for user {user_id}: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving project",
        )
    else:
        return VliResponse.new(
            message="Projects found successfully"
            if len(projects) > 0
            else "No projects was found",
            data={
                "projects": projects,
                "total": len(projects),
            },
        )
