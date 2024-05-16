from http import HTTPStatus as status
from typing import Tuple

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.project_repo import (
    ProjectMutationRepository,
    ProjectQueryRepository,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def update_star_project_status_use_case(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    value: bool,
    auth: Tuple[AuthUser, str],
) -> Response:
    pmr = ProjectMutationRepository(session)
    pqr = ProjectQueryRepository(session)
    user_id = get_user_id_from_auth(auth)

    try:
        _project = pqr.retrieve_project_star(user_id=user_id, project_id=project_id)

        if _project is not None and value is False:
            project_id, updated_at = await pmr.unstar_project(
                project_id=project_id, user_id=user_id
            )

            return VliResponse.new(
                message="User unstar project successfully",
                data={
                    "project_id": project_id,
                    "updated_at": updated_at,
                    "starred": value,
                },
            )
        else:
            star_result = await pmr.star_project(
                project_id=project_id,
                user_id=user_id,
            )

            return VliResponse.new(
                message="User star a new project successfully",
                data={
                    "project_id": star_result.project_id,
                    "updated_at": star_result.updated_at,
                    "starred": True,
                },
            )

    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Staring/Unstaring project failed",
        )
    except Exception as ex:
        logger.error(f"Error during staring user project: {project_id} ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.SERVICE_UNAVAILABLE,
            message="Error during staring/unstaring user project",
        )
