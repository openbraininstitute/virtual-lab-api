from http import HTTPStatus as status

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.project import Project
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def retrieve_user_projects_use_case(
    session: Session, virtual_lab_id: UUID4, user_id: UUID4
) -> JSONResponse | VliError:
    pr = ProjectQueryRepository(session)
    try:
        # TODO: 1. fetch the user projects from keycloak
        # projects_ids = []
        projects = pr.retrieve_projects_batch(
            virtual_lab_id,
            #   projects=projects_ids
        )
        return JSONResponse(
            status_code=status.OK,
            content={
                "message": "Projects found successfully"
                if len(projects) > 0
                else "No projects was found",
                "data": jsonable_encoder(
                    {
                        "projects": [
                            Project(**project.__dict__) for project in projects
                        ],
                        "total": len(projects),
                    }
                ),
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving projects failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during retrieving project for user {user_id}: {virtual_lab_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving project",
        )
