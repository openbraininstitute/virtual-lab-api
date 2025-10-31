from http import HTTPStatus as status
from typing import Tuple

from fastapi.responses import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.common import PageParams
from virtual_labs.domain.project import (
    ProjectsWithWorkspaceResponse,
    ProjectVlOut,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_preference_repo import (
    UserPreferenceQueryRepository,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def retrieve_all_user_projects_use_case(
    session: AsyncSession, auth: Tuple[AuthUser, str], pagination: PageParams
) -> Response:
    prefr = UserPreferenceQueryRepository(session)
    pr = ProjectQueryRepository(session)
    gqr = GroupQueryRepository()

    user_id = get_user_id_from_auth(auth)

    try:
        groups = gqr.retrieve_user_groups(user_id=str(user_id))
        group_ids = [g.id for g in groups]

        results = await pr.retrieve_projects_batch(
            groups=group_ids,
            pagination=pagination,
        )

        projects = [
            ProjectVlOut.model_validate(
                {
                    **p.__dict__,
                    "user_count": 0,
                    "admins": await gqr.a_retrieve_group_user_ids(
                        group_id=p.admin_group_id
                    ),
                }
            )
            for p, _ in results.rows
        ]

        recent_workspace = await prefr.get_user_recent_workspace(user_id)
    except SQLAlchemyError as err:
        print("error", err)
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving projects failed",
        )
    except Exception as ex:
        logger.error(f"Error during retrieving project for user {user_id}: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving project",
        )
    else:
        response_data = ProjectsWithWorkspaceResponse(
            results=projects,
            page=pagination.page,
            size=pagination.size,
            page_size=len(projects),
            total=results.count,
            recent_workspace=recent_workspace,
        )

        return VliResponse.new(
            message="Projects found successfully"
            if len(projects) > 0
            else "No projects was found",
            data=response_data.model_dump(),
        )
