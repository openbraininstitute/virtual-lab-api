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


def update_project_budget_use_case(
    session: Session, virtual_lab_id: UUID4, project_id: UUID4, value: float
) -> Union[JSONResponse, VliError]:
    pr = ProjectMutationRepository(session)
    try:
        # check the user group (if he is project's virtual lab group)
        # check the user permission (admin or member), only admins can do updating budget
        # check if the budget not exceeding the virtual lab budget
        updated_project_id, new_budget, updated_at = pr.update_project_budget(
            virtual_lab_id=virtual_lab_id, project_id=project_id, value=value
        )
        return JSONResponse(
            status_code=status.OK,
            content={
                "message": "Project new budget updated successfully",
                "data": jsonable_encoder(
                    {
                        "updated_project_id": updated_project_id,
                        "new_budget": new_budget,
                        "updated_at": updated_at,
                    }
                ),
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Updating project budget failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during updating project budget ({value}): {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR0,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during updating project budget",
        )
