"""In-process saga primitive for orchestrating compensable side effects.

`CompensationStack` is a per-request stack of async undo callbacks. As a
usecase creates external resources (Keycloak groups, accounting accounts,
etc.) it `push`es the corresponding teardown. On failure the caller invokes
`compensate()` which runs every recorded undo in LIFO order, swallowing
individual errors so one failed teardown does not block the rest.

It is intentionally *not* a durable saga: state lives on the call stack
and is lost if the worker dies. The goal is to replace ad-hoc
`try/except` cleanup blocks with a single, ordered, auditable list.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from loguru import logger

CompensationAction = Callable[[], Awaitable[None]]


class CompensationStack:
    __slots__ = ("_actions",)

    def __init__(self) -> None:
        self._actions: list[CompensationAction] = []

    def push(self, action: CompensationAction) -> None:
        self._actions.append(action)

    def __len__(self) -> int:
        return len(self._actions)

    async def compensate(self, *, reason: str) -> None:
        if not self._actions:
            return
        logger.info(
            f"Running {len(self._actions)} compensation action(s); reason: {reason}"
        )
        # LIFO: undo the most-recent step first.
        while self._actions:
            action = self._actions.pop()
            try:
                await action()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Compensation action failed (continuing): {exc}")
