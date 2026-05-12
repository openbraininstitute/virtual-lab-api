"""Gates that authorize access to a virtual lab."""

from typing import Literal
from uuid import UUID

from fastapi import Depends

from virtual_labs.core.gate.base import forbidden
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants

VlabRole = Literal["admin", "any"]


class VirtualLabGate:
    """FastAPI dependency that authorizes the requester against a
    virtual lab identified by the path parameter `virtual_lab_id`.

    Two modes:

      * ``role="admin"`` — user must be admin of the vlab.
      * ``role="any"`` — user must be admin or member of the vlab.

    On success the gate returns the `AuthUserGrants`, so route
    handlers can name it directly:

        async def endpoint(
            virtual_lab_id: UUID,
            user: AuthUserGrants = Depends(vlab_admin),
        ): ...

    Prefer the module-level `vlab_admin` / `vlab_access` singletons
    over constructing a new instance on every route.
    """

    __slots__ = ("_role",)

    def __init__(self, *, role: VlabRole = "any") -> None:
        self._role = role

    async def __call__(
        self,
        virtual_lab_id: UUID,
        auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
    ) -> AuthUserGrants:
        user, _token = auth
        allowed = (
            user.is_vlab_admin(virtual_lab_id)
            if self._role == "admin"
            else user.has_vlab_access(virtual_lab_id)
        )
        if not allowed:
            raise forbidden(f"vlab:{self._role} on {virtual_lab_id}")
        return user


# Pre-built dependencies for the common cases. FastAPI requires the
# dependency to be a callable; class instances with `__call__` qualify
# and let us keep the configuration colocated with the rule.
virtuallab_admin = VirtualLabGate(role="admin")
virtuallab_access = VirtualLabGate(role="any")
