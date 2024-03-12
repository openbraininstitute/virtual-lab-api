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
from virtual_labs.repositories.group_repo import GroupMutationRepository
from virtual_labs.repositories.project_repo import (
    ProjectMutationRepository,
    ProjectQueryRepository,
)


def delete_project_use_case(
    session: Session, virtual_lab_id: UUID4, project_id: UUID4
) -> Response | VliError:
    pqr = ProjectQueryRepository(session)
    pmr = ProjectMutationRepository(session)
    gmr = GroupMutationRepository()
    # TODO: check the user group (if he is in the project group)
    # TODO: check the user permission (admin/member), only admin can trigger deletion

    project = pqr.retrieve_one_project(
        virtual_lab_id=virtual_lab_id, project_id=project_id
    )
    if project and project.deleted:
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_DELETED,
            http_status_code=status.BAD_REQUEST,
            message="Project already marked as 'deleted'",
        )

    try:
        (
            deleted_project_id,
            admin_group_id,
            member_group_id,
            deleted,
            deleted_at,
        ) = pmr.delete_project(virtual_lab_id=virtual_lab_id, project_id=project_id)
        gmr.delete_group(group_id=admin_group_id)
        gmr.delete_group(group_id=member_group_id)

        return VliResponse.new(
            message="Project marked as deleted successfully",
            data={
                "project_id": deleted_project_id,
                "deleted": deleted,
                "deleted_at": deleted_at,
            },
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Project deletion failed",
        )
    except KeycloakError as ex:
        logger.warning(f"project deletion from KC: {loads(ex.error_message)["error"]}")
        pmr.un_delete_project(virtual_lab_id=virtual_lab_id, project_id=project_id)
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=ex.response_code,
            message="Group deletion failed",
            details=loads(ex.error_message)["error"],
        )

    except Exception as ex:
        logger.error(
            f"Error during deleting the project: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during deleting the project",
        )
