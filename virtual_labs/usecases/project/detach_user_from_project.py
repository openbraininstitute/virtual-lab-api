from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def detach_user_from_project_use_case(
    session: Session,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    user_id: UUID4,
    role: UserRoleEnum,
) -> Response | VliError:
    pr = ProjectQueryRepository(session)

    # validate the data
    # check the user group (if he is in the project group)
    # check the user permission (admin or member), only admins can do detach op
    try:
        pr.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id, project_id=project_id
        )

        # umr.detach_user_from_group(group_id=str(project.group_id), user_id=user_id)
        # TODO: get all user groups where group_id either in project_admin/project_member groups

        return VliResponse.new(
            message="User detached from the project successfully",
            data=None,
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="User detachment from a project failed",
        )
    except Exception as ex:
        logger.error(
            f"Error during detaching user {user_id} from project: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during detaching user from the project",
        )
