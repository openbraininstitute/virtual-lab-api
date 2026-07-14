"""Gate that authorizes access to a Keycloak service group."""

from collections.abc import Iterable

from fastapi import Depends

from virtual_labs.core.gate.base import forbidden
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants


class ServiceGate:
    """FastAPI dependency that authorizes the requester for a named
    Keycloak service (e.g. `entitycore`, `small-scale-simulator`,
    `virtual-lab-svc`).

    The service name is fixed at construction time — service-admin
    endpoints typically scope to one service, and binding the rule at
    import time means a misspelled service is caught at startup rather
    than on the first request.

        admin_router.post(
            "/services/entitycore/...",
            dependencies=[Depends(ServiceGate("entitycore"))],
        )

    For an arbitrary role (anything other than `admin`) pass `role=`:

        Depends(ServiceGate("small-scale-simulator", role="operator"))

    `role` also accepts an iterable of roles with any-of semantics.
    Roles are independent sets in Keycloak (`admin` does not imply
    `maintainer`), so an endpoint open to several tiers must list them:

        Depends(ServiceGate("virtual-lab-svc", role=("admin", "maintainer")))
    """

    __slots__ = ("_service", "_roles")

    def __init__(self, service: str, *, role: str | Iterable[str] = "admin") -> None:
        self._service = service
        self._roles = frozenset([role] if isinstance(role, str) else role)

    async def __call__(
        self,
        auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
    ) -> AuthUserGrants:
        user, _token = auth
        if not (user.grants.services.roles_for(self._service) & self._roles):
            raise forbidden(f"service:{self._service}:{'|'.join(sorted(self._roles))}")
        return user
