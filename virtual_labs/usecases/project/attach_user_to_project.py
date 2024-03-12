from http import HTTPStatus as status
from json import loads

from fastapi.responses import Response
from keycloak import KeycloakError  # type: ignore
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import UserMutationRepository


def attach_user_to_project_use_case(
    session: Session,
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    user_id: UUID4,
    role: UserRoleEnum,
) -> Response | VliError:
    pr = ProjectQueryRepository(session)
    umr = UserMutationRepository()
    # TODO:
    # validate the data
    # check the user group (if he is in the project group)
    # check the user permission (admin or member), only admins can do attach op
    try:
        project = pr.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id, project_id=project_id
        )
        group_id = (
            project.admin_group_id
            if role.value == UserRoleEnum.admin.value
            else project.member_group_id
        )
        umr.attach_user_to_group(user_id=user_id, group_id=str(group_id))

        return VliResponse.new(
            message="User attached to the project successfully",
            data={"project_id": project_id},
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Attaching user to project failed",
        )
    except KeycloakError as ex:
        logger.warning(
            f"Attaching user to KC group failed: {loads(ex.error_message)["error"]}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=ex.response_code,
            message="Attaching user to group failed",
            details=loads(ex.error_message)["error"],
        )
    except Exception as ex:
        logger.error(
            f"Error during attaching user {user_id} to the project: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.SERVICE_UNAVAILABLE,
            message="Error during attaching user to the project",
        )
