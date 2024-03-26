from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.repositories.project_repo import ProjectQueryRepository


async def retrieve_project_budget_use_case(
    session: AsyncSession, virtual_lab_id: UUID4, project_id: UUID4
) -> Response | VliError:
    pr = ProjectQueryRepository(session)
    try:
        project, _ = await pr.retrieve_one_project_strict(virtual_lab_id, project_id)
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
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving project budget",
        )
    else:
        return VliResponse.new(
            message="Project budget fetched successfully",
            data={
                "project_id": project_id,
                "budget": project.budget,
            },
        )
