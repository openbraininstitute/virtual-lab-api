from http import HTTPStatus as status
from typing import Tuple
from uuid import UUID

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import UserNotInList
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.project_repo import (
    ProjectMutationRepository,
    ProjectQueryRepository,
)


async def update_star_project_status_use_case(
    session: Session,
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    value: bool,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    pmr = ProjectMutationRepository(session)
    pqr = ProjectQueryRepository(session)

    try:
        user, _ = auth
        user_id = user.sub

        _project = pqr.retrieve_project_star(
            user_id=UUID(user_id), project_id=project_id
        )

        if _project is not None and value is False:
            project_id, updated_at = pmr.unstar_project(
                project_id=project_id, user_id=UUID(user_id)
            )

            return VliResponse.new(
                message="User unstar project successfully",
                data={
                    "project_id": project_id,
                    "updated_at": updated_at,
                    "starred": value,
                },
            )
        else:
            star_result = pmr.star_project(project_id=project_id, user_id=UUID(user_id))

            return VliResponse.new(
                message="User star a new project successfully",
                data={
                    "project_id": star_result.project_id,
                    "updated_at": star_result.updated_at,
                    "starred": True,
                },
            )

    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Staring/Unstaring project failed",
        )
    except UserNotInList:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=status.NOT_ACCEPTABLE,
            message="Star/Unstar a project not allowed",
        )
    except Exception as ex:
        logger.error(f"Error during staring user project: {project_id} ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.SERVICE_UNAVAILABLE,
            message="Error during staring/unstaring user project",
        )
