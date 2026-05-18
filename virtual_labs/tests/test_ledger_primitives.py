"""Unit tests for the generic ledger primitives in `virtual_labs.core.ledger`.

Pure async, no DB, no Keycloak, no Stripe — exercises the building blocks
that the create-virtual-lab orchestrator (and future create-project)
relies on. Covers:

* `Ledger` LIFO unwind + idempotent compensate.
* `ledger_container` runs unwind on exception, re-raises, single-pass.
* `provision` re-raises `DomainError` unchanged, wraps generic exceptions
  into the caller-supplied `DomainError` subclass.
* `transactional_persistence` maps `IntegrityError` / `SQLAlchemyError`
  to the caller-supplied domain errors.
* `Translator.to_vli_error` echoes only `public_context`; non-whitelisted
  keys stay out of the response payload.
* `build_translator` produces a working `(to_vli_error, decorator)` pair.
"""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.ledger import (
    DomainError,
    Ledger,
    ledger_container,
    provision,
    transactional_persistence,
)
from virtual_labs.core.ledger.translator import (
    TranslationEntry,
    Translator,
    build_translator,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


class _SafeError(DomainError):
    description = "Safe failure"
    safe_context = frozenset({"name"})


class _StepFailedError(DomainError):
    description = "Step exploded"


class _NameConflictError(DomainError):
    description = "Name conflict"


class _DbWriteError(DomainError):
    description = "DB write failed"


def _fake_async_session_factory(
    raise_on_commit: Exception | None = None,
) -> MagicMock:
    """A tiny async-context-manager stand-in for `db.begin()`."""
    session = MagicMock()

    class _Txn:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object,
        ) -> bool:
            if raise_on_commit is not None and exc_type is None:
                raise raise_on_commit
            return False

    session.begin = MagicMock(return_value=_Txn())
    return session


# Ledger


@pytest.mark.asyncio
async def test_ledger_unwinds_lifo() -> None:
    ledger = Ledger()
    calls: list[str] = []

    async def a() -> None:
        calls.append("a")

    async def b() -> None:
        calls.append("b")

    ledger.push(a)
    ledger.push(b)
    await ledger.compensate(reason="t")

    assert calls == ["b", "a"]


@pytest.mark.asyncio
async def test_ledger_compensate_is_idempotent() -> None:
    ledger = Ledger()
    counter = AsyncMock()
    ledger.push(counter)

    await ledger.compensate(reason="first")
    await ledger.compensate(reason="second")

    counter.assert_awaited_once()


@pytest.mark.asyncio
async def test_ledger_swallows_individual_action_failures() -> None:
    ledger = Ledger()
    survivor = AsyncMock()

    async def boom() -> None:
        raise RuntimeError("undo failed")

    ledger.push(boom)
    ledger.push(survivor)

    await ledger.compensate(reason="t")

    survivor.assert_awaited_once()


# ledger_container


@pytest.mark.asyncio
async def test_ledger_container_unwinds_on_exception() -> None:
    calls: list[str] = []

    async def undo() -> None:
        calls.append("undone")

    with pytest.raises(RuntimeError, match="boom"):
        async with ledger_container() as ledger:
            ledger.push(undo)
            raise RuntimeError("boom")

    assert calls == ["undone"]


@pytest.mark.asyncio
async def test_ledger_scope_noop_on_success() -> None:
    undo = AsyncMock()
    async with ledger_container() as ledger:
        ledger.push(undo)

    undo.assert_not_awaited()


# provision


@pytest.mark.asyncio
async def test_provision_passes_domain_error_through_and_unwinds_once() -> None:
    undo = AsyncMock()

    with pytest.raises(_SafeError):
        async with ledger_container() as ledger:
            ledger.push(undo)
            async with provision(ledger, step_name="x", on_failure=_StepFailedError):
                raise _SafeError(name="abc")

    undo.assert_awaited_once()


@pytest.mark.asyncio
async def test_provision_wraps_generic_exception() -> None:
    undo = AsyncMock()

    with pytest.raises(_StepFailedError) as exc_info:
        async with ledger_container() as ledger:
            ledger.push(undo)
            async with provision(ledger, step_name="x", on_failure=_StepFailedError):
                raise ValueError("network blip")

    assert isinstance(exc_info.value.__cause__, ValueError)
    undo.assert_awaited_once()


@pytest.mark.asyncio
async def test_provision_does_not_leak_cause_into_public_context() -> None:
    # The cause stays on __cause__ for logging, not on context for the API.
    try:
        async with ledger_container() as ledger:
            async with provision(ledger, step_name="x", on_failure=_StepFailedError):
                raise RuntimeError("internal Stripe URL leak")
    except _StepFailedError as err:
        assert err.public_context == {}
        assert err.context == {}
    else:  # pragma: no cover - the with-block must raise
        pytest.fail("expected _StepFailedError")


# transactional_persistence


@pytest.mark.asyncio
async def test_transactional_persistence_maps_integrity_error() -> None:
    session = _fake_async_session_factory(
        raise_on_commit=IntegrityError("stmt", {}, Exception("dup"))
    )
    with pytest.raises(_NameConflictError):
        async with transactional_persistence(
            session,
            on_integrity_error=_NameConflictError,
            on_db_error=_DbWriteError,
        ):
            pass


@pytest.mark.asyncio
async def test_transactional_persistence_maps_sqlalchemy_error() -> None:
    session = _fake_async_session_factory(raise_on_commit=SQLAlchemyError("nope"))
    with pytest.raises(_DbWriteError):
        async with transactional_persistence(
            session,
            on_integrity_error=_NameConflictError,
            on_db_error=_DbWriteError,
        ):
            pass


@pytest.mark.asyncio
async def test_transactional_persistence_yields_handle_for_snapshot() -> None:
    session = _fake_async_session_factory()
    async with transactional_persistence(
        session,
        on_integrity_error=_NameConflictError,
        on_db_error=_DbWriteError,
    ) as txn:
        txn.snapshot = "captured"

    assert txn.snapshot == "captured"


# Translator + build_translator


def test_translator_echoes_only_safe_context() -> None:
    t = Translator(
        mapping={
            _SafeError: TranslationEntry(
                VliErrorCode.ENTITY_ALREADY_EXISTS, HTTPStatus.CONFLICT
            ),
        },
        fallback=TranslationEntry(
            VliErrorCode.SERVER_ERROR, HTTPStatus.INTERNAL_SERVER_ERROR
        ),
    )

    err = _SafeError(name="public", cause="secret stripe url")
    vli = t.to_vli_error(err)

    assert isinstance(vli, VliError)
    assert vli.error_code == VliErrorCode.ENTITY_ALREADY_EXISTS
    assert vli.http_status_code == HTTPStatus.CONFLICT
    assert vli.message == _SafeError.description
    assert vli.data == {"name": "public"}
    assert vli.details == "name=public"


def test_translator_falls_back_for_unknown_error() -> None:
    fallback = TranslationEntry(
        VliErrorCode.SERVER_ERROR, HTTPStatus.INTERNAL_SERVER_ERROR
    )
    t = Translator(mapping={}, fallback=fallback)

    class _Unknown(DomainError):
        description = "unknown"

    vli = t.to_vli_error(_Unknown())
    assert vli.error_code == VliErrorCode.SERVER_ERROR
    assert vli.http_status_code == HTTPStatus.INTERNAL_SERVER_ERROR


@pytest.mark.asyncio
async def test_build_translator_decorator_converts_domain_error_to_vli() -> None:
    to_vli, decorate = build_translator(
        {
            _SafeError: TranslationEntry(
                VliErrorCode.ENTITY_ALREADY_EXISTS, HTTPStatus.CONFLICT
            ),
        }
    )

    @decorate
    async def fails() -> None:
        raise _SafeError(name="x")

    with pytest.raises(VliError) as exc_info:
        await fails()

    assert exc_info.value.error_code == VliErrorCode.ENTITY_ALREADY_EXISTS
    assert exc_info.value.http_status_code == HTTPStatus.CONFLICT
    # to_vli_error is the same function used by the decorator.
    assert to_vli(_SafeError(name="x")).error_code == (
        VliErrorCode.ENTITY_ALREADY_EXISTS
    )


@pytest.mark.asyncio
async def test_build_translator_passes_non_domain_exceptions_through() -> None:
    _, decorate = build_translator({})

    @decorate
    async def fails() -> None:
        raise RuntimeError("not ours")

    with pytest.raises(RuntimeError, match="not ours"):
        await fails()
