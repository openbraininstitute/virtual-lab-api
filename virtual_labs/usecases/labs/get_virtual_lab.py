from http import HTTPStatus
from uuid import UUID

from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import (
    VirtualLabDetailExpand,
    VirtualLabWithAdmins,
)
from virtual_labs.domain.user import ShortenedUser
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.infrastructure.kc.models import UserRepresentation


async def get_virtual_lab(
    db: AsyncSession,
    lab_id: UUID4,
    expand: list[VirtualLabDetailExpand] | None = None,
) -> VirtualLabWithAdmins:
    requested = set(expand or [])
    try:
        virtual_lab = (
            await db.scalars(
                select(VirtualLab).where(
                    VirtualLab.id == lab_id,
                    VirtualLab.deleted.is_(False),
                )
            )
        ).one()

        admins: list[UUID4] | None = None
        if VirtualLabDetailExpand.admins in requested:
            members = await KeycloakRealm.a_get_group_members(
                group_id=str(virtual_lab.admin_group_id)
            )
            admins = [UUID(UserRepresentation(**member).id) for member in members]

        owner: ShortenedUser | None = None
        if VirtualLabDetailExpand.owner in requested:
            owner = ShortenedUser.model_validate(
                UserRepresentation(
                    **await KeycloakRealm.a_get_user(str(virtual_lab.owner_id))
                )
            )

        return VirtualLabWithAdmins.model_validate(virtual_lab).model_copy(
            update={
                "created_by": virtual_lab.created_by,
                "admins": admins,
                "owner": owner,
            }
        )
    except (NoResultFound, SQLAlchemyError) as error:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        ) from error
    except VliError as error:
        raise error
