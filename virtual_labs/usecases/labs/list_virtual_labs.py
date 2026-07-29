"""`GET /virtual-labs` — paginated tenant (membership) listing.

The shape of this endpoint is intentionally rich because it backs the
main "labs you can see" view in the UI. Three orthogonal axes shape
the result set, and a fourth axis controls ordering:

  * **ownership filter** — ``scope`` (``all`` / ``self`` /
    ``external``). ``all`` is the default and surfaces every lab the
    user can access; ``self`` keeps only labs the user owns;
    ``external`` keeps only labs the user can access but does *not*
    own.
  * **role filter** — ``admin_access_only``. Restricts the candidate
    set to labs where the user is admin, derived from
    ``auth.grants.virtual_labs.admin``.
  * **search** — case-insensitive substring match on ``name``.
  * **ordering** — ``order_by`` selects the dimension
    (``created_at`` / ``updated_at`` / ``name`` / ``owner``),
    ``order_direction`` selects the direction.

The two ``scope`` parameters share a name on purpose — they live on
the same conceptual axis (ownership). One filters, the other sorts.
"""

from __future__ import annotations

from enum import StrEnum
from http import HTTPStatus
from typing import Any
from uuid import UUID

from loguru import logger
from pydantic import Field
from sqlalchemy import case, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.ordering import order_clauses
from virtual_labs.domain.common import (
    ListResponse,
    OrderBy,
    OrderDirection,
    PaginationRequest,
    PaginationResponse,
    WorkspaceOrderBy,
)
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, Grants
from virtual_labs.usecases.labs._user_labs_helpers import (
    enrich_many,
    list_vlabs_by_id,
)


class Scope(StrEnum):
    """Ownership filter for the listing.

    * ``ALL`` — every accessible lab (default).
    * ``SELF`` — only labs the requester owns.
    * ``EXTERNAL`` — only labs the requester does *not* own.
    """

    ALL = "all"
    SELF = "self"
    EXTERNAL = "external"


class ListVirtualLabsQuery(PaginationRequest):
    scope: Scope = Scope.ALL
    admin_access_only: bool = False
    order_by: WorkspaceOrderBy = WorkspaceOrderBy.UPDATED_AT
    order_direction: OrderDirection = OrderDirection.DESC
    query: str | None = Field(default=None, min_length=1, max_length=200)


def _build_order_clauses(
    order_by: WorkspaceOrderBy,
    direction: OrderDirection,
    user_id: object,
) -> tuple[ColumnElement[Any], ...]:
    """Translate the ordering enums into SQLAlchemy clauses.

    For ``OWNER`` we sort on a synthetic 0/1 column (0 = self-owned,
    1 = external) so ``ASC`` puts the user's own labs first. The
    other dimensions share the stable cascade in `core.ordering`.
    """
    if order_by is WorkspaceOrderBy.OWNER:
        owner_expr = case((VirtualLab.owner_id == user_id, 0), else_=1)
        primary = (
            owner_expr.asc() if direction is OrderDirection.ASC else owner_expr.desc()
        )
        return primary, VirtualLab.updated_at.desc(), VirtualLab.created_at.desc()

    return order_clauses(VirtualLab, OrderBy(order_by.value), direction)


def _scope_condition(scope: Scope, user_id: object) -> ColumnElement[bool] | None:
    """Translate the `scope` enum into a single `WHERE` fragment.
    `ALL` returns `None` so the filter is simply omitted."""
    if scope is Scope.SELF:
        return VirtualLab.owner_id == user_id
    if scope is Scope.EXTERNAL:
        return VirtualLab.owner_id != user_id
    return None


async def _resolve_candidate_ids(
    *,
    user: AuthUserGrants,
    session: AsyncSession,
    admin_access_only: bool,
) -> set[UUID]:
    """Build the JWT-derived candidate set for the IN-clause.

    The fast path reads `auth.grants.virtual_labs` from the JWT — no
    network calls. Two defensive layers keep the endpoint reliable
    when the realm is not configured to expose the ``groups`` claim
    via ``/userinfo``:

      1. **Owned-lab inclusion.** The lab the user owns is fetched
         from the database and added to the set. DB ownership is
         authoritative and survives any Keycloak misconfiguration,
         so a user always sees their own lab.
      2. **KC user-groups fallback.** If ``user.groups`` is empty
         (the JWT carries no group claim at all) we issue *one*
         Keycloak admin call to retrieve the user's groups directly
         and parse them with the same `Grants` parser. This adds
         one network round-trip only when the fast path returned
         nothing — production realms with the mapper never pay it.
    """

    def _vlab_set(g: Grants) -> set[UUID]:
        return set(g.virtual_labs.admin if admin_access_only else g.virtual_labs.all)

    candidate_ids = _vlab_set(user.grants)

    if not user.groups:
        # JWT lacks the groups claim entirely — go to KC.
        try:
            kc_groups = await KeycloakRealm.a_get_user_groups(user_id=str(user.id))
            candidate_ids |= _vlab_set(
                Grants.from_groups(str(g["path"]) for g in kc_groups)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"KC user-groups fallback failed for {user.id}: {exc}; "
                "continuing with DB-ownership-only scope"
            )

    # Owned lab is always a member of the user's scope (except
    # `EXTERNAL`, which `_scope_condition` later filters out).
    owned = await session.scalar(
        select(VirtualLab).where(
            VirtualLab.owner_id == user.id,
            VirtualLab.deleted.is_(False),
        )
    )
    if owned is not None:
        candidate_ids.add(UUID(str(owned.id)))

    return candidate_ids


async def list_virtual_labs_use_case(
    *,
    session: AsyncSession,
    auth: tuple[AuthUserGrants, str],
    scope: Scope,
    admin_access_only: bool,
    order_by: WorkspaceOrderBy,
    order_direction: OrderDirection,
    query: str | None,
    pagination: PaginationRequest,
) -> ListResponse[VirtualLabDetails]:
    user, _token = auth

    candidate_ids = await _resolve_candidate_ids(
        user=user,
        session=session,
        admin_access_only=admin_access_only,
    )

    # Ownership filter applied at the DB layer so it composes with
    # the role and search filters in a single `WHERE`.
    extra: list[ColumnElement[bool]] = []
    ownership = _scope_condition(scope, user.id)
    if ownership is not None:
        extra.append(ownership)

    ordering = _build_order_clauses(order_by, order_direction, user.id)

    try:
        rows, total = await list_vlabs_by_id(
            session,
            vlab_ids=candidate_ids,
            query=query,
            pagination=pagination,
            extra_conditions=extra,
            order_by=ordering,
        )
    except SQLAlchemyError as exc:
        logger.exception(f"DB error listing tenant vlabs for {user.id}: {exc}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Failed to list virtual labs",
        )

    items = await enrich_many(rows, session)
    return ListResponse[VirtualLabDetails](
        data=items,
        pagination=PaginationResponse(
            page=pagination.page,
            page_size=len(items),
            total_items=total,
        ),
    )
