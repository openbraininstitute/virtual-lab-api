import uuid
from http import HTTPStatus as status

from fastapi.responses import Response
from httpx import AsyncClient
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.project import Project, ProjectCreationBody
from virtual_labs.repositories.group_repo import GroupMutationRepository
from virtual_labs.repositories.labs import get_virtual_lab
from virtual_labs.repositories.project_repo import ProjectMutationRepository
from virtual_labs.shared.utils.random_string import gen_random_string


async def create_new_project_use_case(
    session: Session,
    *,
    virtual_lab_id: UUID4,
    user_id: UUID4,
    payload: ProjectCreationBody,
    httpx_clt: AsyncClient,
) -> Response | VliError:
    pr = ProjectMutationRepository(session)
    gmr = GroupMutationRepository()

    try:
        get_virtual_lab(session, virtual_lab_id)
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="Virtual lab not found",
        )
    """ 
        TODO: 1. check if the user in admin group of the virtual lab to allow him to create a project, (this can be a decorator)
        TODO: 2. when create the groups, attach the current user to the group, 
        TODO: 3. when create the groups, attach the list of the users (included_members) to the current member group,
        TODO: 4. when create the groups, attach the VL admin users list of current admin group,
    """
    project_id: UUID4 = uuid.uuid4()
    nexus_project_id = gen_random_string(10)  # grab it from nexus api

    try:
        admin_group_id = gmr.create_project_group(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            payload=payload,
            role=UserRoleEnum.admin,
        )

        member_group_id = gmr.create_project_group(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            payload=payload,
            role=UserRoleEnum.member,
        )
    except Exception as ex:
        logger.error(f"Error during creating new group in KC: ({ex})")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="KC Group creation failed",
        )

    try:
        assert admin_group_id is not None
        assert member_group_id is not None

        project = pr.create_new_project(
            id=project_id,
            payload=payload,
            virtual_lab_id=virtual_lab_id,
            nexus_project_id=nexus_project_id,
            admin_group_id=admin_group_id,
            member_group_id=member_group_id,
            owner_id=user_id,
            # nexus_project_id=nexus_project.id,
        )

        # TODO: add include_members list to the group in KC
    except AssertionError:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Admin/Member group_id failed to be generated",
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
    else:
        return VliResponse.new(
            message="Project created successfully",
            data={
                "project": Project(**project.__dict__),
            },
        )
