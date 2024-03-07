from http import HTTPStatus as status
from typing import Union

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.repositories.project_repo import ProjectMutationRepository


def delete_project_use_case(
    session: Session, virtual_lab_id: UUID4, project_id: UUID4
) -> Union[JSONResponse, VliError]:
    pr = ProjectMutationRepository(session)
    # check the user group (if he is in the project group)
    # check the user permission (admin or member), only admins can do deletion
    try:
        deleted_project_id, deleted, deleted_at = pr.delete_project(
            virtual_lab_id=virtual_lab_id, project_id=project_id
        )
        return JSONResponse(
            status_code=status.OK,
            content={
                "message": "Project marked as deleted successfully",
                "data": jsonable_encoder(
                    {
                        "project_id": deleted_project_id,
                        "deleted": deleted,
                        "deleted_at": deleted_at,
                    }
                ),
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Project deletion failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during deleting the project: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during deleting the project",
        )
