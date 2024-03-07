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


def retrieve_projects_count_per_virtual_lab_use_case(
    session: Session, virtual_lab_id: UUID4
) -> Union[JSONResponse, VliError]:
    pr = ProjectQueryRepository(session)
    try:
        count = pr.retrieve_projects_per_lab_count(virtual_lab_id)
        return JSONResponse(
            status_code=status.OK,
            content={
                "message": "project count per virtual lab fetched successfully",
                "data": jsonable_encoder({"count": count}),
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="retrieving count of projects per virtual lab failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during counting projects per virtual lab: {virtual_lab_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR0,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during counting projects per virtual lab",
        )
