"""`GET /virtual-labs/me` — the requester's owned virtual lab.

Returns the single lab the user owns (the one created via
`POST /virtual-labs`), enriched with `projects_count` and course
metadata. Returns `None` in the response payload when the user has
no owned lab — clients render that as the "create your lab" state.
"""

from __future__ import annotations

from http import HTTPStatus

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.usecases.labs._user_labs_helpers import enrich_many


async def get_my_virtual_lab_use_case(
    *,
    session: AsyncSession,
    auth: tuple[AuthUserGrants, str],
) -> VirtualLabDetails | None:
    user, _token = auth
    try:
        owned = await session.scalar(
            select(VirtualLab).where(
                VirtualLab.owner_id == user.id,
                ~VirtualLab.deleted,
            )
        )
    except SQLAlchemyError as exc:
        logger.exception(f"DB error fetching owned vlab for {user.id}: {exc}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Failed to load your virtual lab",
        )

    if owned is None:
        return None
    return (await enrich_many([owned], session))[0]
