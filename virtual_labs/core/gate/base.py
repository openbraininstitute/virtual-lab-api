"""Shared primitives for the `core.gate` authorization layer.

The gate layer is a lightweight replacement for the legacy
`core.authorization` decorators. Where the old layer pulled arguments
from `kwargs` via introspection, made several Keycloak round-trips to
enumerate group members, and mapped half a dozen exception types to
`VliError`, the new layer is composed of small FastAPI dependencies
that:

  * receive the requester as an `AuthUserGrants` from
    `parse_auth_grants` — group memberships are already known,
  * delegate the actual decision to the structured `Grants` view,
  * raise exactly one error (`forbidden`) on denial.

Errors raised by `parse_auth_grants` itself (invalid/expired token)
propagate before any gate runs, so gates only see authenticated users
and only need to answer "is this user allowed?".
"""

from http import HTTPStatus

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode


def forbidden(reason: str) -> VliError:
    """Construct the canonical denial error.

    `reason` is opaque to clients (it goes into `details`); use it to
    record why a specific gate denied access so logs and error bodies
    explain which rule fired.
    """
    return VliError(
        error_code=VliErrorCode.NOT_ALLOWED_OP,
        http_status_code=HTTPStatus.FORBIDDEN,
        message="Not authorized to perform this action",
        details=reason,
    )
