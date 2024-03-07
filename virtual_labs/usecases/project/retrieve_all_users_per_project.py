from http import HTTPStatus as status

from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.repositories.user_repo import UserRepository


def retrieve_all_users_per_project_use_case(
    session: Session,
    project_id: UUID4,
) -> JSONResponse | VliError:
    ur = UserRepository("master")
    try:
        # TODO:
        # 1. fetch project group from kc
        # 2. get both members and admins
        # 3. consider pagination
        # 4. return the list + count
        ur.retrieve_users_per_project(project_id)
        return JSONResponse(
            status_code=status.OK,
            content={
                "message": "Users found successfully",
                # "data": jsonable_encoder(users),
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving users for a project failed",
        )
    except Exception as ex:
        logger.error(f"Error during retrieving users per project: {project_id} ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR0,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving users per project",
        )
