"""Gate that authorizes access to a Keycloak service group."""

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
    """

    __slots__ = ("_service", "_role")

    def __init__(self, service: str, *, role: str = "admin") -> None:
        self._service = service
        self._role = role

    async def __call__(
        self,
        auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
    ) -> AuthUserGrants:
        user, _token = auth
        if not user.has_service_role(self._service, self._role):
            raise forbidden(f"service:{self._service}:{self._role}")
        return user
