from http import HTTPStatus as status
from uuid import uuid4

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
from virtual_labs.repositories.project_repo import (
    ProjectMutationRepository,
    ProjectQueryRepository,
)


async def create_new_project_use_case(
    session: Session,
    *,
    virtual_lab_id: UUID4,
    user_id: UUID4,
    payload: ProjectCreationBody,
    httpx_clt: AsyncClient,
) -> Response | VliError:
    project_id: UUID4 = uuid4()
    pmr = ProjectMutationRepository(session)
    pqr = ProjectQueryRepository(session)
    gmr = GroupMutationRepository()

    try:
        get_virtual_lab(session, virtual_lab_id)
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="Virtual lab not found",
        )

    try:
        pqr.retrieve_one_project_by_name(name=payload.name)
    except Exception as ex:
        logger.error(f"Error during retrieving the project ({ex})")
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=status.BAD_REQUEST,
            message="Another project with the same name already exists",
        )

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

        assert admin_group_id is not None
        assert member_group_id is not None

    except AssertionError:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Admin/Member group_id failed to be generated",
        )
    except Exception as ex:
        logger.error(f"Error during creating new group in KC: ({ex})")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="KC Group creation failed",
        )

    try:
        nexus_project_id = await instantiate_nexus_project(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            description=payload.description,
            admin_group_id=admin_group_id,
            member_group_id=member_group_id,
        )
        # TODO: add include_members list to the group in KC

    except NexusError as ex:
        logger.error(f"Error during reverting project instance due nexus error ({ex})")
        gmr.delete_group(group_id=admin_group_id)
        gmr.delete_group(group_id=member_group_id)

        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Nexus Project creation failed",
            details=ex.type,
        )

    try:
        project = pmr.create_new_project(
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
