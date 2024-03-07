from http import HTTPStatus as status

from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def retrieve_users_per_project_count_use_case(
    session: Session, project_id: UUID4
) -> JSONResponse | VliError:
    pr = ProjectQueryRepository(session)
    try:
        # TODO:
        # use kc instead of db
        # fetch from keycloak the users (admin + members) of the project
        pr.retrieve_project_users_count(project_id)
        return JSONResponse(
            status_code=status.OK,
            content={
                "message": f"count users per project {project_id} fetched successfully",
                # "data": jsonable_encoder({"count": count}),
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="retrieving users per project failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during retrieving users per project count: {project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR0,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving users per project",
        )
