from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.repositories.project_repo import ProjectQueryRepository


async def retrieve_projects_count_per_virtual_lab_use_case(
    session: AsyncSession, virtual_lab_id: UUID4
) -> Response | VliError:
    pr = ProjectQueryRepository(session)

    try:
        count = await pr.retrieve_projects_per_lab_count(
            virtual_lab_id,
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving count of projects per virtual lab failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during counting projects per virtual lab: {virtual_lab_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during counting projects per virtual lab",
        )
    else:
        return VliResponse.new(
            message="Project count per virtual lab fetched successfully",
            data={
                "virtual_lab_id": virtual_lab_id,
                "total": count,
            },
        )
