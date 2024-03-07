from http import HTTPStatus as status
from typing import Union

from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4, EmailStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.repositories.user_repo import UserRepository


def detach_user_from_project_use_case(
    session: Session, virtual_lab_id: UUID4, project_id: UUID4, user_email: EmailStr
) -> Union[JSONResponse, VliError]:
    ur = UserRepository("master")
    # validate the data
    # check the user group (if he is in the project group)
    # check the user permission (admin or member), only admins can do detach op
    try:
        ur.detach_user_from_project(
            virtual_lab_id=virtual_lab_id, project_id=project_id, user_email=user_email
        )

        return JSONResponse(
            status_code=status.OK,
            content={
                "message": "User detached from the project successfully",
                # "data": result,
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="User detachment from a project failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during detaching user {user_email} from project: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR0,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during detaching user from the project",
        )
