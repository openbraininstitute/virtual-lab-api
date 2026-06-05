"""`GET /virtual-labs/awaiting` — paginated pending vlab invitations.

Returns the virtual labs the requester has been invited to but has
not yet accepted, joined with the invite id so the client can act on
each entry (`POST /invites/{invite_id}/accept`).

Pagination is enforced at the SQL layer rather than slicing in
Python: a user with hundreds of pending invites would otherwise load
all of them into memory just to return ten.
"""

from __future__ import annotations

from http import HTTPStatus

from loguru import logger
from sqlalchemy import and_, false, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.common import (
    ListResponse,
    PaginationRequest,
    PaginationResponse,
)
from virtual_labs.domain.labs import VirtualLabDetails, VirtualLabWithInviteDetails
from virtual_labs.infrastructure.db.models import VirtualLab, VirtualLabInvite
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.shared.utils.auth import get_user_email_from_auth


async def list_pending_virtual_labs_use_case(
    *,
    session: AsyncSession,
    auth: tuple[AuthUserGrants, str],
    pagination: PaginationRequest,
) -> ListResponse[VirtualLabWithInviteDetails]:
    email = get_user_email_from_auth(auth)

    conditions = and_(
        VirtualLabInvite.user_email == email,
        VirtualLabInvite.accepted == false(),
        VirtualLab.deleted == false(),
    )

    base = (
        select(VirtualLab, VirtualLabInvite.id.label("invite_id"))
        .join(VirtualLabInvite, VirtualLabInvite.virtual_lab_id == VirtualLab.id)
        .where(conditions)
    )

    try:
        total = (
            await session.scalar(
                select(func.count())
                .select_from(VirtualLabInvite)
                .join(VirtualLab, VirtualLabInvite.virtual_lab_id == VirtualLab.id)
                .where(conditions)
            )
        ) or 0

        rows = (
            await session.execute(
                base.order_by(VirtualLabInvite.id.desc())
                .offset(pagination.offset)
                .limit(pagination.page_size)
            )
        ).all()
    except SQLAlchemyError as exc:
        logger.exception(f"DB error fetching pending invites for {email}: {exc}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Failed to load pending invitations",
        )

    items = [
        VirtualLabWithInviteDetails(
            **VirtualLabDetails.model_validate(lab).model_dump(),
            invite_id=invite_id,
        )
        for lab, invite_id in rows
    ]

    return ListResponse[VirtualLabWithInviteDetails](
        data=items,
        pagination=PaginationResponse(
            page=pagination.page,
            page_size=len(items),
            total_items=total,
        ),
    )
