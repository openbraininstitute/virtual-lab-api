from datetime import datetime
from http import HTTPStatus as status
from json import loads
from typing import List, Tuple

from fastapi.responses import Response
from keycloak import KeycloakError  # type: ignore
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import (
    EntityNotFound,
    ForbiddenOperation,
)
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.project import (
    AddUserProjectDetails,
    AddUserToProjectIn,
    AttachUserFailedOperation,
    EmailFailure,
    ProjectUserOperationsResponse,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.services.attach_user_groups import (
    get_project_and_vl_groups,
    manage_user_groups,
    send_project_emails,
)
from virtual_labs.shared.utils.auth import get_user_metadata


async def attach_users_to_project(
    session: AsyncSession,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    users: List[AddUserToProjectIn],
    auth: Tuple[AuthUser, str],
) -> Response:
    # subscription_repo = SubscriptionRepository(db_session=session)
    pqr = ProjectQueryRepository(session)
    failed_operations: List[AttachUserFailedOperation] = []
    email_failures: List[EmailFailure] = []
    added_users: List[AddUserProjectDetails] = []
    updated_users: List[AddUserProjectDetails] = []

    try:
        # Verify user has active subscription
        # user_id = get_user_id_from_auth(auth)
        # subscription = await subscription_repo.get_active_subscription_by_user_id(
        #     user_id=user_id,
        #     subscription_type="paid",
        # )
        # if not subscription:
        #     raise ForbiddenOperation()

        project, virtual_lab = await pqr.retrieve_one_project_strict(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
        )

        inviter = get_user_metadata(auth_user=auth[0])
        inviter_name = (
            inviter["full_name"] if inviter["full_name"] else inviter["username"]
        )

        (
            unique_users_map,
            project_admin_group_id,
            project_member_group_id,
            existing_proj_admin_ids,
            existing_proj_member_ids,
        ) = await get_project_and_vl_groups(
            project=project,
            virtual_lab=virtual_lab,
            users=users,
        )

        if not unique_users_map:
            return VliResponse.new(
                message="No unique, non-owner users provided to process.",
                data=ProjectUserOperationsResponse(
                    project_id=project_id,
                    added_users=[],
                    updated_users=[],
                    failed_operations=[],
                    email_sending_failures=[],
                    processed_at=datetime.now(),
                ),
            )

        (
            added_users,
            updated_users,
            failed_operations,
            user_to_email_map,
        ) = await manage_user_groups(
            users_map=unique_users_map,
            project_admin_group_id=project_admin_group_id,
            project_member_group_id=project_member_group_id,
            existing_proj_admin_ids=existing_proj_admin_ids,
            existing_proj_member_ids=existing_proj_member_ids,
            project_id=project_id,
        )

        if user_to_email_map:
            email_failures = await send_project_emails(
                user_to_email_map=user_to_email_map,
                project_id=project_id,
                project_name=str(project.name),
                virtual_lab_id=virtual_lab_id,
                virtual_lab_name=str(virtual_lab.name),
                inviter_name=inviter_name,
            )
    except EntityNotFound as ex:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=status.BAD_REQUEST,
            message="One or more users are not members of the parent Virtual Lab.",
            data=ex.data,
        )
    except SQLAlchemyError as db_error:
        logger.error(f"Database error retrieving project/VL {project_id}: {db_error}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving project or virtual lab failed",
        )
    except KeycloakError as error:
        error_detail = "Unknown Keycloak Error during group membership fetch"
        try:
            error_detail = loads(error.error_message).get("error", error_detail)
        except Exception:
            pass
        logger.warning(
            f"Keycloak fetch for project/VL {project_id} failed: {error_detail}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=error.response_code or status.BAD_GATEWAY,
            message=f"Processing users failed due to Keycloak issue: {error_detail}",
        )
    except ForbiddenOperation:
        raise VliError(
            error_code=VliErrorCode.FORBIDDEN_OPERATION,
            http_status_code=status.FORBIDDEN,
            message="User does not have an active subscription: {ex}",
        )
    except VliError:
        raise
    except Exception as ex:
        logger.exception(ex)
        logger.error(
            f"Unexpected error during attach/update users for project: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Unexpected error during processing users for project",
        )
    else:
        return VliResponse.new(
            message="Users processed for project attachment.",
            data=ProjectUserOperationsResponse(
                project_id=project_id,
                added_users=added_users,
                updated_users=updated_users,
                failed_operations=failed_operations,
                email_sending_failures=email_failures,
                processed_at=datetime.now(),
            ),
        )
