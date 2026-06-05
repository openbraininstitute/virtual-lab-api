"""Async context managers that hide every `try/except` needed to drive a
ledger-backed use case:

* `ledger_container`        — yields a fresh `Ledger`, unwinds on any exception.
* `provision`               — runs one external-provisioning step under the
                              ledger, mapping unexpected failures to a typed
                              `DomainError` subclass.
* `transactional_persistence` — runs a single `db.begin()` block, mapping
                              `IntegrityError` / `SQLAlchemyError` to typed
                              `DomainError` subclasses chosen by the caller.

Reusable across modules (virtual lab, project, …). The caller supplies the
module-specific `DomainError` subclass to raise — everything else is generic.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

from loguru import logger
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import DomainError
from .ledger import Ledger


async def _shielded_unwind(ledger: Ledger, *, reason: str) -> None:
    """Run `ledger.compensate` shielded from outer cancellation so a
    `CancelledError` does not abort the unwind mid-way and leak resources.
    """
    await asyncio.shield(ledger.compensate(reason=reason))


@asynccontextmanager
async def ledger_container() -> AsyncIterator[Ledger]:
    """Yield a fresh `Ledger`. On any exception inside the scope, unwind
    every recorded action in LIFO order and re-raise the original
    exception.

    `CancelledError` propagates immediately but the unwind is shielded so
    in-flight teardowns finish before the cancellation is observed by the
    caller. `Ledger.compensate` is idempotent, so a nested unwind followed
    by this one is safe.
    """
    ledger = Ledger()
    try:
        yield ledger
    except asyncio.CancelledError:
        await _shielded_unwind(ledger, reason="ledger scope cancelled")
        raise
    except BaseException:
        await ledger.compensate(reason="ledger scope aborted")
        raise


@asynccontextmanager
async def provision(
    ledger: Ledger,
    *,
    step_name: str,
    on_failure: type[DomainError],
) -> AsyncIterator[None]:
    """Run one external-provisioning step under the ledger.

    * `DomainError` raised inside the body passes through unchanged (the
      body has already classified the failure) but still triggers a
      ledger unwind.
    * Any other non-cancellation exception is logged in full, the ledger
      is unwound, and the caller-supplied `on_failure` `DomainError`
      subclass is raised. The raw exception message is NOT placed on the
      response payload — only the typed domain error's `description` is
      surfaced to clients.
    * `CancelledError` propagates after a shielded unwind so partial
      provisioning is rolled back before the caller observes the cancel.
    """
    try:
        yield
    except DomainError:
        await ledger.compensate(reason=step_name)
        raise
    except asyncio.CancelledError:
        await _shielded_unwind(ledger, reason=f"{step_name} cancelled")
        raise
    except Exception as ex:
        logger.exception(f"{step_name} failed: {ex}")
        await ledger.compensate(reason=step_name)
        raise on_failure() from ex


@asynccontextmanager
async def transactional_persistence(
    db: AsyncSession,
    *,
    on_integrity_error: type[DomainError],
    on_db_error: type[DomainError],
) -> AsyncIterator[SimpleNamespace]:
    """Run a single `db.begin()` transaction. Map `IntegrityError` to the
    caller's `on_integrity_error` (typically a "race-window conflict"
    domain error) and any other `SQLAlchemyError` to `on_db_error`.

    Yields a `SimpleNamespace` so the body can attach values (e.g. a
    pre-commit snapshot) that survive after the transaction commits and
    the ORM instances detach.
    """
    handle = SimpleNamespace()
    try:
        async with db.begin():
            yield handle
    except IntegrityError as err:
        logger.error(f"DB integrity error: {err}")
        raise on_integrity_error() from err
    except SQLAlchemyError as err:
        logger.error(f"DB write failed: {err}")
        raise on_db_error() from err
