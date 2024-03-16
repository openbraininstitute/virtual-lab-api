from http import HTTPStatus as status
from typing import Dict, cast

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import UserNotInList
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import (
    ProjectMutationRepository,
    ProjectQueryRepository,
)
from virtual_labs.shared.utils.is_user_in_list import is_user_in_list
from virtual_labs.shared.utils.uniq_list import uniq_list


def update_star_project_status_use_case(
    session: Session, *, virtual_lab_id: UUID4, user_id: UUID4, project_id: UUID4
) -> Response | VliError:
    pmr = ProjectMutationRepository(session)
    pqr = ProjectQueryRepository(session)
    gqr = GroupQueryRepository()

    try:
        project, _ = pqr.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id, project_id=project_id
        )
        users = gqr.retrieve_group_users(group_id=str(project.member_group_id))
        uniq_users = uniq_list([cast(Dict[str, str], u)["id"] for u in users])
        is_user_in_list(list_=uniq_users, user_id=str(user_id))

        _project = pqr.retrieve_project_star(user_id=user_id, project_id=project_id)

        if _project is not None:
            project_id, updated_at = pmr.unstar_project(
                project_id=project_id, user_id=user_id
            )

            return VliResponse.new(
                message="User unstar project successfully",
                data={
                    "project_id": project_id,
                    "starred_at": updated_at,
                    "starred": False,
                },
            )
        else:
            star_result = pmr.star_project(project_id=project_id, user_id=user_id)

            return VliResponse.new(
                message="User star a new project successfully",
                data={
                    "project_id": star_result.project_id,
                    "starred_at": star_result.updated_at,
                    "starred": True,
                },
            )

    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Staring/Unstaring project failed",
        )
    except UserNotInList:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=status.NOT_ACCEPTABLE,
            message="Star/Unstar a project not allowed",
        )
    except Exception as ex:
        logger.error(f"Error during staring user project: {project_id} ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.SERVICE_UNAVAILABLE,
            message="Error during staring/unstaring user project",
        )
