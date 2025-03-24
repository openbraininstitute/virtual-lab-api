from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.labs import UserStats
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.invite_repo import InviteQueryRepository
from virtual_labs.repositories.labs import (
    get_user_virtual_lab,
    get_virtual_labs_where_user_is_member,
)
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.shared.utils.auth import (
    get_user_email_from_auth,
    get_user_id_from_auth,
)


async def get_user_stats(
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> Response:
    """Get all statistics for a user, including virtual labs, pending invites, and projects."""
    try:
        user_id = get_user_id_from_auth(auth)
        email = get_user_email_from_auth(auth)

        group_repo = GroupQueryRepository()
        invite_repo = InviteQueryRepository(session)
        project_repo = ProjectQueryRepository(session)

        user_groups = await group_repo.a_retrieve_user_groups(user_id=str(user_id))
        group_ids = [g.id for g in user_groups]

        owned_labs = await get_user_virtual_lab(session, user_id)
        owned_labs_count = 1 if owned_labs else 0

        member_labs = await get_virtual_labs_where_user_is_member(session, user_id)
        member_labs_count = len(member_labs)

        pending_invites_count = await invite_repo.get_pending_invites_for_user(email)

        owned_projects_count = await project_repo.get_owned_projects_count(user_id)
        member_projects_count = await project_repo.get_member_projects_count(
            user_id, group_ids
        )

        # Create the UserStats object
        stats = UserStats(
            owned_labs_count=owned_labs_count,
            member_labs_count=member_labs_count,
            pending_invites_count=pending_invites_count,
            owned_projects_count=owned_projects_count,
            member_projects_count=member_projects_count,
            total_labs=owned_labs_count + member_labs_count,
            total_projects=owned_projects_count + member_projects_count,
        )

        return VliResponse.new(
            message="User statistics retrieved successfully",
            data=stats.model_dump(),
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error when retrieving user stats: {e}")
        raise VliError(
            message="Failed to retrieve user statistics due to database error",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=VliErrorCode.DATABASE_ERROR,
        )
    except Exception as e:
        logger.error(f"Unexpected error when retrieving user stats: {e}")
        raise VliError(
            message="Failed to retrieve user statistics",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=VliErrorCode.SERVER_ERROR,
        )
