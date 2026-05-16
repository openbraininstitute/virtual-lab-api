"""The `Ledger` records compensating actions for in-progress external work.

As a use case provisions resources (Keycloak groups, accounting accounts,
Stripe customers, …) it `push`es the corresponding undo. On failure the
caller invokes `compensate()` which runs every recorded undo in LIFO order,
swallowing individual errors so one failed undo does not block the rest.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from loguru import logger

LedgerAction = Callable[[], Awaitable[None]]


class Ledger:
    __slots__ = ("_actions",)

    def __init__(self) -> None:
        self._actions: list[LedgerAction] = []

    def push(self, action: LedgerAction) -> None:
        self._actions.append(action)

    def __len__(self) -> int:
        return len(self._actions)

    async def compensate(self, *, reason: str) -> None:
        if not self._actions:
            return
        logger.info(
            f"Unwinding {len(self._actions)} ledger action(s); reason: {reason}"
        )
        while self._actions:
            action = self._actions.pop()
            try:
                await action()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Ledger action failed (continuing): {exc}")


__all__ = ["Ledger", "LedgerAction"]
