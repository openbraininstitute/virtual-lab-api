"""Internal helpers for safe field access on Stripe SDK objects.

Stripe's `StripeObject` extends `dict`, which means `obj.items` resolves to
the inherited `dict.items` method rather than the data field of the same
name. Going through `__getitem__` / `.get()` avoids that collision and
also returns `None` (instead of raising `AttributeError`) for absent fields.

Both `helpers.py` and `subscription_period.py` use these helpers so the
two modules can stay consistent without duplicating the duck-typing logic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def field_value(source: Any, key: str) -> Any:
    """Read `source[key]` (Mapping) or `source.key` (object) safely.

    Returns `None` for `source=None` or a missing key/attribute. Tolerates
    StripeObject (dict subclass), plain dicts, dataclasses, and `SimpleNamespace`.
    """
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key)
    get = getattr(source, "get", None)
    if callable(get):
        try:
            return get(key)
        except TypeError:
            # `.get` exists but isn't a Mapping-style accessor — fall through
            pass
    return getattr(source, key, None)


def first_item(source: Any) -> Any:
    """First element of `source` if it's a non-empty list-like sequence, else None."""
    if isinstance(source, Sequence) and not isinstance(source, str):
        return source[0] if source else None
    return None


def expandable_id(value: Any) -> str | None:
    """Return the resource id from `ExpandableField[T] = T | str | None`."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return field_value(value, "id")  # type: ignore[no-any-return]
