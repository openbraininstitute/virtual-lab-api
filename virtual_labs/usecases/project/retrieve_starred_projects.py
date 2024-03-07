from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.project import Project
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def retrieve_starred_projects_use_case(
    session: Session, user_id: UUID4
) -> Response | VliError:
    pr = ProjectQueryRepository(session)
    try:
        projects = pr.retrieve_starred_projects_per_user(user_id)

        return VliResponse.new(
            message="Starred projects found successfully",
            data={
                "projects": [
                    {
                        **Project(**project.__dict__).__dict__,
                        "starred_at": star.created_at,
                    }
                    for star, project in projects
                ],
                "total": len(projects),
            },
        )

    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving starred project failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during retrieving starred projects for user: {user_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving starred projects",
        )
