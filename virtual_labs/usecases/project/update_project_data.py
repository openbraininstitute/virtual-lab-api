from http import HTTPStatus as status
from typing import Tuple

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.project import Project, ProjectBody
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.project_repo import ProjectMutationRepository


async def update_project_data(
    session: Session,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    payload: ProjectBody,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    pmr = ProjectMutationRepository(session)

    try:
        (project,) = pmr.update_project_data(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            payload=payload,
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Updating project failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during updating project data: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during updating project",
        )
    else:
        return VliResponse.new(
            message="Project data updated successfully",
            data={
                "project": Project(**project.__dict__),
            },
        )
