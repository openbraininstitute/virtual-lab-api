from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.project import Project, ProjectCreationModel
from virtual_labs.repositories.labs import get_virtual_lab
from virtual_labs.repositories.project_repo import ProjectMutationRepository
from virtual_labs.shared.utils.random_string import gen_random_string


def create_new_project_use_case(
    session: Session, virtual_lab_id: UUID4, payload: ProjectCreationModel
) -> Response | VliError:
    pr = ProjectMutationRepository(session)

    try:
        get_virtual_lab(session, virtual_lab_id)
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="virtual lab not found",
        )
    """
    TODO: 
        we are using flat groups structure
        1. we should fetch all the vl admins
        2. when the user try to access the project we check the user id in the project or parent lab groups
        create a group in keycloak and attach vl admins, current user, to the group
        create a project in nexus
    """
    try:
        nexus_project_id = gen_random_string(10)  # grab it from nexus api
        project = pr.create_new_project(
            payload=payload, nexus_id=nexus_project_id, virtual_lab_id=virtual_lab_id
        )

        # TODO: add include_members list to the group in KC
        return VliResponse.new(
            message="Project created successfully",
            data={
                "project": Project(**project.__dict__),
            },
        )
    except IntegrityError:
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=status.BAD_REQUEST,
            message="Project already exists",
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Project creation failed",
        )
    except Exception as ex:
        logger.error(f"Error during creating new project ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during creating a new project",
        )
