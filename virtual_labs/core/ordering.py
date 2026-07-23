"""Stable-ordering clauses for the paginated list endpoints.

Timestamp orderings cascade into the other timestamp and name
ordering falls back to `updated_at`, so pages of rows with identical
sort keys keep a stable order between requests. Every listing that
sorts on `created_at` / `updated_at` / `name` builds its clauses here
so the cascade rule cannot diverge between endpoints.
"""

from typing import Any

from sqlalchemy import func
from sqlalchemy.sql import ColumnElement

from virtual_labs.domain.common import OrderBy, OrderDirection


def order_clauses(
    model: Any,
    order_by: OrderBy,
    direction: OrderDirection,
) -> tuple[ColumnElement[Any], ...]:
    """`model` is any mapped class with `created_at`, `updated_at` and
    `name` columns (`VirtualLab`, `Project`)."""
    asc = direction is OrderDirection.ASC

    if order_by is OrderBy.CREATED_AT:
        col = model.created_at
        return (col.asc() if asc else col.desc(),)

    if order_by is OrderBy.NAME:
        col = func.lower(model.name)
        return (col.asc() if asc else col.desc(), model.updated_at.desc())

    # OrderBy.UPDATED_AT (default)
    col = model.updated_at
    return (col.asc() if asc else col.desc(), model.created_at.desc())
