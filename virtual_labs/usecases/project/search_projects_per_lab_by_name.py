from http import HTTPStatus as status
from typing import Union

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.project import Project
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def search_projects_per_virtual_lab_by_name_use_case(
    session: Session, virtual_lab_id: UUID4, user_id: UUID4, query_term: str | None
) -> Union[JSONResponse, VliError]:
    pr = ProjectQueryRepository(session)
    print(virtual_lab_id, user_id, query_term)
    if not query_term:
        raise VliError(
            error_code=VliErrorCode.INVALID_PARAMETER,
            http_status_code=status.BAD_REQUEST,
            message="no search query provided",
        )
    try:
        # TODO: provide projects from only the user allow to access
        # TODO: provide projects_ids
        projects = pr.search(query_term=query_term, projects_ids=None).all()
        return JSONResponse(
            status_code=status.OK,
            content={
                "message": f"projects with {query_term} found successfully"
                if len(projects) > 0
                else "no projects was found",
                "data": jsonable_encoder(
                    {
                        "projects": [
                            Project(**project.__dict__) for project in projects
                        ],
                        "total": len(projects),
                    }
                ),
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="searching for projects failed",
        )
    except Exception as ex:
        print(ex)
        logger.error(f"Error during searching for projects in {virtual_lab_id} ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR0,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during searching for project",
        )
