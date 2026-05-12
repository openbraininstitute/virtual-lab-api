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
    (``creation_date`` / ``update_date`` / ``scope``), ``order_direction``
    selects the direction. ``scope`` orders by self-owned vs external,
    which is useful for tabs that want self-owned labs at the top
    without imposing a separate query.

The two ``scope`` parameters share a name on purpose — they live on
the same conceptual axis (ownership). One filters, the other sorts.
"""

from __future__ import annotations

from enum import Enum
from http import HTTPStatus
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import case
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.common import PageParams, PaginatedResponse
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, Grants
from virtual_labs.repositories import labs as labs_repository
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.usecases.labs._user_labs_helpers import (
    enrich_many,
    list_vlabs_by_id,
)


class Scope(str, Enum):
    """Ownership filter for the listing.

    * ``ALL`` — every accessible lab (default).
    * ``SELF`` — only labs the requester owns.
    * ``EXTERNAL`` — only labs the requester does *not* own.
    """

    ALL = "all"
    SELF = "self"
    EXTERNAL = "external"


class OrderBy(str, Enum):
    CREATION_DATE = "creation_date"
    UPDATE_DATE = "update_date"
    SCOPE = "scope"


class OrderDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


def _build_order_clauses(
    order_by: OrderBy,
    direction: OrderDirection,
    user_id: object,
) -> tuple[ColumnElement[Any], ...]:
    """Translate the ordering enums into SQLAlchemy clauses.

    For ``SCOPE`` we sort on a synthetic 0/1 column (0 = self-owned,
    1 = external) so ``ASC`` puts the user's own labs first. The
    timestamp orderings cascade into ``created_at`` as a secondary
    key to avoid swapping rows with identical updated/created
    timestamps.
    """
    asc = direction is OrderDirection.ASC

    if order_by is OrderBy.SCOPE:
        scope_expr = case((VirtualLab.owner_id == user_id, 0), else_=1)
        primary = scope_expr.asc() if asc else scope_expr.desc()
        # Within each scope bucket, keep the recency feel.
        return primary, VirtualLab.updated_at.desc(), VirtualLab.created_at.desc()

    if order_by is OrderBy.CREATION_DATE:
        col = VirtualLab.created_at
        return (col.asc() if asc else col.desc(),)

    # UPDATE_DATE (default)
    col = VirtualLab.updated_at
    return (col.asc() if asc else col.desc(), VirtualLab.created_at.desc())


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
            kc_groups = await GroupQueryRepository().a_retrieve_user_groups(
                user_id=str(user.id)
            )
            candidate_ids |= _vlab_set(Grants.from_groups(g.path for g in kc_groups))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"KC user-groups fallback failed for {user.id}: {exc}; "
                "continuing with DB-ownership-only scope"
            )

    # Owned lab is always a member of the user's scope (except
    # `EXTERNAL`, which `_scope_condition` later filters out).
    owned = await labs_repository.get_user_virtual_lab(db=session, owner_id=user.id)
    if owned is not None:
        candidate_ids.add(UUID(str(owned.id)))

    return candidate_ids


async def list_tenant_virtual_labs_use_case(
    *,
    session: AsyncSession,
    auth: tuple[AuthUserGrants, str],
    scope: Scope,
    admin_access_only: bool,
    order_by: OrderBy,
    order_direction: OrderDirection,
    query: str | None,
    pagination: PageParams,
) -> PaginatedResponse[VirtualLabDetails]:
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

    order_clauses = _build_order_clauses(order_by, order_direction, user.id)

    try:
        rows, total = await list_vlabs_by_id(
            session,
            vlab_ids=candidate_ids,
            query=query,
            pagination=pagination,
            extra_conditions=extra,
            order_by=order_clauses,
        )
    except SQLAlchemyError as exc:
        logger.exception(f"DB error listing tenant vlabs for {user.id}: {exc}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Failed to list virtual labs",
        )

    items = await enrich_many(rows, ProjectQueryRepository(session=session))
    return PaginatedResponse.build(
        items=items,
        total=total,
        page=pagination.page,
        size=pagination.size,
    )
