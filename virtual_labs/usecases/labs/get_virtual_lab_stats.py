import asyncio
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import VirtualLabStats
from virtual_labs.repositories import labs as repository
from virtual_labs.repositories.group_repo import GroupQueryRepository


async def get_virtual_lab_stats(
    db: AsyncSession,
    virtual_lab_id: UUID,
) -> VirtualLabStats:
    """Get statistics for a virtual lab."""
    gqr = GroupQueryRepository()
    try:
        virtual_lab = await repository.get_undeleted_virtual_lab(db, virtual_lab_id)
        stats = await repository.get_virtual_lab_stats(db, virtual_lab_id)

        admin_users, member_users = await asyncio.gather(
            gqr.a_retrieve_group_users(group_id=str(virtual_lab.admin_group_id)),
            gqr.a_retrieve_group_users(group_id=str(virtual_lab.member_group_id)),
        )
        total_members = len(set(admin_users + member_users))

        return VirtualLabStats(
            virtual_lab_id=virtual_lab_id,
            total_projects=stats["total_projects"],
            total_members=total_members,
            total_pending_invites=stats["total_pending_invites"],
            admin_users=[UUID(user.id) for user in admin_users],
            member_users=[UUID(user.id) for user in member_users],
        )

    except SQLAlchemyError as error:
        logger.exception(error)
        raise VliError(
            message="Error retrieving virtual lab stats",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from error
    except Exception as error:
        logger.exception(error)
        raise VliError(
            message="Unexpected error retrieving virtual lab stats",
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from error
