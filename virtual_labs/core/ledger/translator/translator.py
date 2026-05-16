"""Generic translator that turns a module's `DomainError` into the API-facing `VliError`"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, TypeVar

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode

from ..errors import DomainError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class TranslationEntry:
    code: VliErrorCode
    status: HTTPStatus


ErrorMapping = dict[type[DomainError], TranslationEntry]


def _details_from_context(context: dict[str, Any]) -> str | None:
    if not context:
        return None
    return ", ".join(f"{k}={v}" for k, v in context.items())


class Translator:
    __slots__ = ("_mapping", "_fallback")

    def __init__(self, mapping: ErrorMapping, *, fallback: TranslationEntry) -> None:
        self._mapping = mapping
        self._fallback = fallback

    def to_vli_error(self, err: DomainError) -> VliError:
        entry = self._mapping.get(type(err), self._fallback)
        public = err.public_context
        return VliError(
            message=err.description,
            error_code=entry.code,
            http_status_code=entry.status,
            details=_details_from_context(public),
            data=public or None,
        )


DEFAULT_FALLBACK = TranslationEntry(
    code=VliErrorCode.SERVER_ERROR,
    status=HTTPStatus.INTERNAL_SERVER_ERROR,
)


def build_translator(
    mapping: ErrorMapping,
    *,
    fallback: TranslationEntry = DEFAULT_FALLBACK,
) -> tuple[
    Callable[[DomainError], VliError],
    Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]],
]:
    """Module-level convenience: one mapping dict → `(to_vli_error, decorator)`.

    The returned decorator is generic in the wrapped function's return
    type so type-checkers see `create_virtual_lab(...) -> VirtualLabDetails`
    rather than `Any` after decoration.
    """
    translator = Translator(mapping, fallback=fallback)

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> T:
            try:
                return await fn(*args, **kwargs)
            except DomainError as err:
                raise translator.to_vli_error(err) from err

        return _wrapped

    return translator.to_vli_error, decorator
