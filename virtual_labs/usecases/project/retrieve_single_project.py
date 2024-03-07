from http import HTTPStatus as status

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import MultipleResultsFound, NoResultFound, SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.project import Project
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def retrieve_single_project_use_case(
    session: Session, virtual_lab_id: UUID4, project_id: UUID4
) -> JSONResponse | VliError:
    pr = ProjectQueryRepository(session)
    # TODO: check the user access to the project
    try:
        project = pr.retrieve_one_project(virtual_lab_id, project_id)
        return JSONResponse(
            status_code=status.OK,
            content={
                "message": "Project found successfully",
                "data": jsonable_encoder({"project": Project(**project.__dict__)}),
            },
        )
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="No project found",
        )
    except MultipleResultsFound:
        raise VliError(
            error_code=VliErrorCode.MULTIPLE_ENTITIES_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="Multiple projects found",
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving project failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during retrieve project: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR0,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving project",
        )
