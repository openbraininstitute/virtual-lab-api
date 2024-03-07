from http import HTTPStatus as status
from typing import Union

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.repositories.project_repo import (
    ProjectMutationRepository,
    ProjectQueryRepository,
)


def update_star_project_status_use_case(
    session: Session, *, virtual_lab_id: UUID4, user_id: UUID4, project_id: UUID4
) -> Union[JSONResponse, VliError]:
    pmr = ProjectMutationRepository(session)
    pqr = ProjectQueryRepository(session)

    # TODO: check if the user really part of the project
    try:
        project = pqr.retrieve_project_star(user_id=user_id, project_id=project_id)

        if project is not None:
            result = pmr.unstar_project(project_id=project_id, user_id=user_id)
            return JSONResponse(
                status_code=status.OK,
                content={
                    "message": f"User unstar project {project_id} successfully",
                    "data": jsonable_encoder(
                        {
                            "project_id": result[0],
                        }
                    ),
                },
            )
        else:
            result = pmr.star_project(project_id=project_id, user_id=user_id)
            return JSONResponse(
                status_code=status.OK,
                content={
                    "message": f"User star a new project {project_id} successfully",
                    "data": jsonable_encoder(
                        {
                            "project_id": result.project_id,
                            "stared_at": result.created_at,
                        }
                    ),
                },
            )

    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Staring/Unstaring project failed",
        )
    except Exception as ex:
        logger.error(f"Error during staring user project: {project_id} ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.SERVICE_UNAVAILABLE,
            message="Error during staring/unstaring user project",
        )
