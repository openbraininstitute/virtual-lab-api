from http import HTTPStatus as status
from typing import Union

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def retrieve_project_budget_use_case(
    session: Session, virtual_lab_id: UUID4, project_id: UUID4
) -> Union[JSONResponse, VliError]:
    pr = ProjectQueryRepository(session)
    try:
        budget = pr.retrieve_project(virtual_lab_id, project_id).budget
        return JSONResponse(
            status_code=status.OK,
            content={
                "message": "Project budget fetched successfully",
                "data": jsonable_encoder({"budget": budget}),
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving budget of project failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during retrieving project budget: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR0,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving project budget",
        )
