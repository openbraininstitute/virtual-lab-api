from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import (
    BudgetExceedLimit,
)
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.repositories.project_repo import (
    ProjectMutationRepository,
    ProjectQueryRepository,
)


async def update_project_budget_use_case(
    session: AsyncSession,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    value: float,
) -> Response | VliError:
    pmr = ProjectMutationRepository(session)
    pqr = ProjectQueryRepository(session)

    try:
        _, virtual_lab = await pqr.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id, project_id=project_id
        )

        if value > virtual_lab.budget:
            raise BudgetExceedLimit("Project budget exceed max limit")

        updated_project_id, new_budget, updated_at = await pmr.update_project_budget(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            value=value,
        )

    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Updating project budget failed",
        )
    except BudgetExceedLimit:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=status.NOT_ACCEPTABLE,
            message="Update project budget exceed limit",
        )
    except Exception as ex:
        logger.error(
            f"Error during updating project budget ({value}): {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during updating project budget",
        )
    else:
        return VliResponse.new(
            message="Project new budget updated successfully",
            data={
                "project_id": updated_project_id,
                "new_budget": new_budget,
                "updated_at": updated_at,
            },
        )
