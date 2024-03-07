from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def check_project_existence_use_case(
    session: Session, query_term: str | None
) -> Response | VliError:
    pr = ProjectQueryRepository(session)
    if not query_term:
        raise VliError(
            error_code=VliErrorCode.INVALID_PARAMETER,
            http_status_code=status.BAD_REQUEST,
            message="No search query provided",
        )
    try:
        projects_count = pr.check(query_term=query_term).count()

        return VliResponse.new(
            message=(
                f"Project with name {query_term} already exist"
                if projects_count > 0
                else f"No project was found by {query_term}"
            ),
            data={"exist": projects_count != 0},
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Searching for projects failed",
        )
    except Exception as ex:
        print(ex)
        logger.error(f"Error during searching for project existence ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during searching for project existence",
        )
