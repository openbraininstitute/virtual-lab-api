import asyncio
from http import HTTPStatus as status
from typing import Tuple
from uuid import uuid4

from fastapi.responses import Response
from keycloak import KeycloakError  # type: ignore
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.project import ProjectCreationBody, ProjectVlOut
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
from virtual_labs.shared.utils.auth import get_user_id_from_auth
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

    try:
        await get_undeleted_virtual_lab(session, virtual_lab_id)
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

    try:
        project = await pmr.create_new_project(
            id=project_id,
            payload=payload,
            virtual_lab_id=virtual_lab_id,
            admin_group_id=admin_group["id"],
            member_group_id=member_group["id"],
            owner_id=user_id,
        )

        # transfer all credits to first project if this is user's first project
        balance_added = False
        if user_projects_count == 0 and settings.ACCOUNTING_BASE_URL is not None:
            try:
                logger.info(
                    f"Transferring all credits to first project {project_id} for user {user_id}"
                )

                vlab_balance_response = await accounting_cases.get_virtual_lab_balance(
                    virtual_lab_id=virtual_lab_id, include_projects=False
                )
                current_balance = float(vlab_balance_response.data.balance)

                if current_balance > 0:
                    await accounting_cases.assign_project_budget(
                        virtual_lab_id=virtual_lab_id,
                        project_id=project_id,
                        amount=current_balance,
                    )
                    balance_added = True
                    logger.info(
                        f"Successfully transferred {current_balance} credits to project {project_id}"
                    )
                else:
                    logger.info(
                        f"No credits to transfer for project {project_id} (balance: {current_balance})"
                    )

            except Exception as ex:
                logger.error(
                    f"Failed to transfer credits to first project {project_id}: {ex}"
                )
                balance_added = False

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
                "balance_added": balance_added,
            },
        )
