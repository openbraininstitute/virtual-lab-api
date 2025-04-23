import asyncio
from http import HTTPStatus as status
from typing import List, Tuple
from uuid import uuid4

from fastapi.responses import Response
from keycloak import KeycloakError  # type: ignore
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.nexus_error import NexusError
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.project import (
    EmailFailure,
    ProjectCreationBody,
    ProjectVlOut,
)
from virtual_labs.external.nexus.project_instance import instantiate_nexus_project
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.group_repo import (
    GroupMutationRepository,
)
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
from virtual_labs.repositories.project_repo import (
    ProjectMutationRepository,
    ProjectQueryRepository,
)
from virtual_labs.repositories.user_repo import (
    UserMutationRepository,
)
from virtual_labs.services.attach_user_groups import (
    get_project_and_vl_groups,
    manage_user_groups,
    send_project_emails,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth, get_user_metadata
from virtual_labs.usecases import accounting as accounting_cases


async def create_new_project_use_case(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    payload: ProjectCreationBody,
    auth: Tuple[AuthUser, str],
) -> Response:
    pmr = ProjectMutationRepository(session)
    pqr = ProjectQueryRepository(session)
    gmr = GroupMutationRepository()
    umr = UserMutationRepository()

    project_id: UUID4 = uuid4()
    user_id = get_user_id_from_auth(auth)

    user_projects_count = await pqr.get_owned_projects_count(user_id=user_id)
    if user_projects_count >= settings.MAX_PROJECTS_NUMBER:
        raise VliError(
            error_code=VliErrorCode.LIMIT_EXCEEDED,
            http_status_code=status.BAD_REQUEST,
            message="You have reached the maximum limit of 20 projects",
        )

    # Check if user has reached the projects limit
    user_projects_count = await pqr.get_owned_projects_count(user_id=user_id)
    if user_projects_count >= settings.MAX_PROJECTS_NUMBER:
        raise VliError(
            error_code=VliErrorCode.LIMIT_EXCEEDED,
            http_status_code=status.BAD_REQUEST,
            message="You have reached the maximum limit of 20 projects",
        )

    try:
        vlab = await get_undeleted_virtual_lab(session, virtual_lab_id)
        if bool(
            await pqr.check_project_exists_by_name_per_vlab(
                vlab_id=virtual_lab_id,
                query_term=payload.name,
            )
        ):
            raise

    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="Virtual lab not found",
        )
    except Exception as ex:
        logger.error(
            f"Error during retrieving the Virtual lab or Project with same name exist ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=status.BAD_REQUEST,
            message="Another project with the same name already exists",
        )

    try:
        admin_group, member_group = await asyncio.gather(
            gmr.a_create_project_group(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
                payload=payload,
                role=UserRoleEnum.admin,
            ),
            gmr.a_create_project_group(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
                payload=payload,
                role=UserRoleEnum.member,
            ),
        )

        assert admin_group is not None
        assert member_group is not None

        await umr.a_attach_user_to_group(
            user_id=user_id,
            group_id=admin_group["id"],
        )

    except AssertionError:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Admin/Member group_id failed to be generated",
        )
    except KeycloakError as ex:
        logger.error(f"Error during creating/attaching to group in KC: ({ex})")
        raise VliError(
            error_code=ex.response_code or VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="KC Group creation/attaching failed",
        )
    except Exception as ex:
        logger.error(f"Error during creating/attaching to group in KC: ({ex})")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="KC Group creation/attaching failed",
        )

    try:
        nexus_project_id = await instantiate_nexus_project(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            description=payload.description,
            admin_group_name=admin_group["name"],
            member_group_name=member_group["name"],
            auth=auth,
        )
    except NexusError as ex:
        logger.error(f"Error during creating project instance due nexus error ({ex})")
        gmr.delete_group(group_id=admin_group["id"])
        gmr.delete_group(group_id=member_group["id"])

        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_GATEWAY,
            message="Nexus Project creation failed",
            details=ex.type,
        )

    if settings.ACCOUNTING_BASE_URL is not None:
        try:
            await accounting_cases.create_project_account(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
                name=payload.name,
            )
        except Exception as ex:
            logger.error(f"Error when creating project account {ex}")
            raise VliError(
                error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
                http_status_code=status.BAD_GATEWAY,
                message="Project account creation failed",
            )
    total_added_users = 0
    email_failures: List[EmailFailure] = []
    error_adding_users = None

    try:
        project = await pmr.create_new_project(
            id=project_id,
            payload=payload,
            virtual_lab_id=virtual_lab_id,
            nexus_project_id=nexus_project_id,
            admin_group_id=admin_group["id"],
            member_group_id=member_group["id"],
            owner_id=user_id,
        )
        try:
            if payload.include_members:
                inviter = get_user_metadata(auth_user=auth[0])
                inviter_name = (
                    inviter["full_name"]
                    if inviter["full_name"]
                    else inviter["username"]
                )
                await session.refresh(vlab)
                (
                    unique_users_map,
                    project_admin_group_id,
                    project_member_group_id,
                    existing_proj_admin_ids,
                    existing_proj_member_ids,
                ) = await get_project_and_vl_groups(
                    project=project,
                    virtual_lab=vlab,
                    users=payload.include_members,
                )
                (added_users, _, _, user_to_email_map) = await manage_user_groups(
                    users_map=unique_users_map,
                    project_admin_group_id=project_admin_group_id,
                    project_member_group_id=project_member_group_id,
                    existing_proj_admin_ids=existing_proj_admin_ids,
                    existing_proj_member_ids=existing_proj_member_ids,
                    project_id=UUID4(str(project.id)),
                )
                total_added_users = len(added_users)
                if user_to_email_map:
                    email_failures = await send_project_emails(
                        user_to_email_map=user_to_email_map,
                        project_id=project_id,
                        project_name=str(project.name),
                        virtual_lab_id=virtual_lab_id,
                        virtual_lab_name=str(vlab.name),
                        inviter_name=inviter_name,
                    )
        except Exception as ex:
            logger.error(f"Error during attaching users to project {project_id} ({ex})")
            error_adding_users = str(ex.__str__())
    except IntegrityError:
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=status.BAD_REQUEST,
            message="Project already exists",
        )
    except SQLAlchemyError as ex:
        logger.exception(f"Database error creating new project: {ex}")
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
        project_out = ProjectVlOut.model_validate(project)
        project_out.user_count = total_added_users + 1
        return VliResponse.new(
            message="Project created successfully",
            data={
                "project": project_out,
                "virtual_lab_id": virtual_lab_id,
                "failed_invites": email_failures,
                "error_adding_users": error_adding_users,
            },
        )
