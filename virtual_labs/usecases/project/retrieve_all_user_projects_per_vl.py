from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.project import VirtualLabModel
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def retrieve_all_user_projects_per_vl_use_case(
    session: Session, virtual_lab_id: UUID4, user_id: UUID4
) -> Response | VliError:
    pr = ProjectQueryRepository(session)
    gqr = GroupQueryRepository()

    try:
        groups = gqr.retrieve_user_groups(user_id=str(user_id))
        group_ids = [g.id for g in groups]
        projects_vl_tuple = pr.retrieve_projects_per_vl_batch(
            virtual_lab_id=virtual_lab_id, groups=group_ids
        )
        projects = [
            {
                **p.__dict__,
                "virtual_lab": VirtualLabModel(**v.__dict__),
            }
            for p, v in projects_vl_tuple
        ]
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving vl/projects failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during retrieving projects for user {user_id} per virtual lab: {virtual_lab_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving vl/projects",
        )
    else:
        return VliResponse.new(
            message="Virtual lab Projects found successfully"
            if len(projects) > 0
            else "No projects was found",
            data={
                "projects": projects,
                "total": len(projects),
            },
        )
