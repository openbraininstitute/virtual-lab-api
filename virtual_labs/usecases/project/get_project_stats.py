import asyncio
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy.exc import MultipleResultsFound, NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.project import ProjectStats
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository


async def get_project_stats(
    db: AsyncSession,
    project_id: UUID,
) -> ProjectStats:
    """Get comprehensive statistics for a project."""
    gqr = GroupQueryRepository()
    pqr = ProjectQueryRepository(session=db)
    try:
        try:
            project, _ = await pqr.retrieve_one_project_by_id(project_id)
        except (NoResultFound, MultipleResultsFound) as error:
            raise VliError(
                message="Project not found",
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
                http_status_code=HTTPStatus.NOT_FOUND,
            ) from error

        stats = await pqr.get_project_stats(project_id)

        admin_users, member_users = await asyncio.gather(
            gqr.a_retrieve_group_users(group_id=str(project.admin_group_id)),
            gqr.a_retrieve_group_users(group_id=str(project.member_group_id)),
        )

        total_members = len(set(user.id for user in admin_users + member_users))
        return ProjectStats(
            project_id=project_id,
            total_stars=stats["total_stars"],
            total_bookmarks=stats["total_bookmarks"],
            total_pending_invites=stats["total_pending_invites"],
            total_notebooks=stats["total_notebooks"],
            total_members=total_members,
            admin_users=[UUID(user.id) for user in admin_users],
            member_users=[UUID(user.id) for user in member_users],
        )

    except SQLAlchemyError as error:
        logger.exception(error)
        raise VliError(
            message="Error retrieving project stats",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from error
    except Exception as error:
        logger.exception(error)
        raise VliError(
            message="Unexpected error retrieving project stats",
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from error
