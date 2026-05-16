"""Generic `DomainError` base used by every module wired through the
ledger/translator. Subclass per business rule, set a `description`, set
`safe_context` to the subset of context keys safe to echo back to clients,
and register the subclass in the module's `Translator` mapping.
"""

from __future__ import annotations

from typing import Any, ClassVar


class DomainError(Exception):
    """Base class for module-level business-rule failures.

    Subclasses:

    * Set `description` — rendered as the API `VliError.message`.
    * Set `safe_context` — keys from the constructor `**context` that are
      safe to surface in the API response (`VliError.data`/`details`).
      Anything not listed is kept in the in-process exception for logging
      but never echoed to the client. Defaults to an empty set, i.e. no
      context is exposed unless explicitly opted in.

    Use keyword-only context, e.g. `raise FooError(name=name, owner_id=...)`.
    """

    description: ClassVar[str] = "Operation failed"
    safe_context: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, **context: Any) -> None:
        super().__init__(self.description)
        self.context = context

    @property
    def public_context(self) -> dict[str, Any]:
        """Subset of `context` that the translator may put on the response."""
        return {k: v for k, v in self.context.items() if k in self.safe_context}
