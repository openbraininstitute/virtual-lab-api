"""Gates that authorize access to a project."""

from typing import Literal
from uuid import UUID

from fastapi import Depends

from virtual_labs.core.gate.base import forbidden
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants

ProjectRole = Literal["admin", "any"]


class ProjectGate:
    """FastAPI dependency that authorizes the requester against a
    project identified by the path parameter `project_id`.

    Parameters:

      * ``role="admin"`` — user must be admin of the project.
      * ``role="any"`` — user must be admin or member of the project.
      * ``include_vlab_admin=True`` — additionally allow admins of the
        project's parent vlab. The parent vlab id is read from the JWT
        (the project group path is `/proj/{vlab_id}/{project_id}/...`),
        so this rule still requires zero DB round-trips.

    Use the module-level `project_admin` / `project_access` /
    `workspace_access` singletons for the common shapes.
    """

    __slots__ = ("_role", "_include_vlab_admin")

    def __init__(
        self, *, role: ProjectRole = "any", include_vlab_admin: bool = False
    ) -> None:
        self._role = role
        self._include_vlab_admin = include_vlab_admin

    async def __call__(
        self,
        project_id: UUID,
        auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
    ) -> AuthUserGrants:
        user, _token = auth

        # 1. Direct project membership.
        direct = (
            user.is_project_admin(project_id)
            if self._role == "admin"
            else user.has_project_access(project_id)
        )
        if direct:
            return user

        # 2. Optional fallback: admin of the project's parent vlab.
        if self._include_vlab_admin and user.is_vlab_admin_of_project(project_id):
            return user

        raise forbidden(
            f"project:{self._role}"
            f"{':+vlab_admin' if self._include_vlab_admin else ''}"
            f" on {project_id}"
        )


project_admin = ProjectGate(role="admin")
project_access = ProjectGate(role="any")
workspace_access = ProjectGate(role="any", include_vlab_admin=True)
