"""Ordering clauses shared by the admin list endpoints.

Same cascade pattern as `usecases/labs/list_virtual_labs.py`: timestamp
orderings fall back to `created_at` and name ordering falls back to
`updated_at` so pages of identical primary keys stay stable.
"""

from typing import Any

from sqlalchemy import func
from sqlalchemy.sql import ColumnElement

from virtual_labs.domain.admin import AdminOrderBy
from virtual_labs.domain.common import OrderDirection


def order_clauses(
    model: Any,
    order_by: AdminOrderBy,
    direction: OrderDirection,
) -> tuple[ColumnElement[Any], ...]:
    """`model` is any mapped class with `created_at`, `updated_at` and
    `name` columns (`VirtualLab`, `Project`)."""
    asc = direction is OrderDirection.ASC

    if order_by is AdminOrderBy.CREATED_AT:
        col = model.created_at
        return (col.asc() if asc else col.desc(),)

    if order_by is AdminOrderBy.NAME:
        col = func.lower(model.name)
        return (col.asc() if asc else col.desc(), model.updated_at.desc())

    # UPDATED_AT (default)
    col = model.updated_at
    return (col.asc() if asc else col.desc(), model.created_at.desc())
