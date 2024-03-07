from http import HTTPStatus as status
from typing import Union

from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4, EmailStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.repositories.user_repo import UserRepository
from virtual_labs.shared.utils.random_string import gen_random_string


def attach_user_to_project_use_case(
    session: Session, *, virtual_lab_id: UUID4, project_id: UUID4, user_email: EmailStr
) -> Union[JSONResponse, VliError]:
    ur = UserRepository("master")
    # TODO:
    # validate the data
    # check the user group (if he is in the project group)
    # check the user permission (admin or member), only admins can do attach op
    try:
        user_email = gen_random_string()
        ur.attach_user_to_project(
            virtual_lab_id=virtual_lab_id, project_id=project_id, user_email=user_email
        )

        return JSONResponse(
            status_code=status.OK,
            content={
                "message": "User attached to the project successfully",
                # "data": result,
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Attaching user to project failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during attaching user {user_email} to the project: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.SERVICE_UNAVAILABLE,
            message="Error during attaching user to the project",
        )
