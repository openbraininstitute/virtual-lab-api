"""Gates that authorize access to a project."""

from typing import Literal
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.gate.base import forbidden
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Project
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants

ProjectRole = Literal["admin", "any"]


class ProjectGate:
    """FastAPI dependency that authorizes the requester against a
    project identified by the path parameter `project_id`.

    Parameters:

      * ``role="admin"`` — user must be admin of the project
      * ``role="any"`` — user must be admin or member of the project
      * ``include_vlab_admin=True`` — additionally allow admins of the
        project's parent vlab. The parent vlab id is read from the JWT
        (the project group path is `/proj/{vlab_id}/{project_id}/...`)
        on the fast path, so a vlab admin who is also in the project's KC
        group is authorized with zero DB round-trips. When the JWT does
        *not* carry the project's vlab path, e.g. a vlab admin who was
        never attached to the project's KC group, or a historical project
        created outside the normal flow, the parent vlab is resolved from
        the DB and re-checked against the user's vlab-admin grants, this
        keeps the common case network-free while closing the silent-deny
        gap for vlab admins not present in the project group.

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
        session: AsyncSession = Depends(default_session_factory),
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
        if self._include_vlab_admin:
            # fast path: the JWT knows the project's parent vlab.
            if user.is_vlab_admin_of_project(project_id):
                return user
            # slow path: the JWT doesn't carry the project's vlab path
            # (vlab admin not in the project's KC group, or a historical
            # project), resolve the parent vlab from the DB and re-check.
            vlab_id = await self._resolve_parent_vlab(session, project_id)
            if vlab_id is not None and user.is_vlab_admin(vlab_id):
                return user

        raise forbidden(
            f"project:{self._role}"
            f"{':+vlab_admin' if self._include_vlab_admin else ''}"
            f" on {project_id}"
        )

    @staticmethod
    async def _resolve_parent_vlab(
        session: AsyncSession, project_id: UUID
    ) -> UUID | None:
        """Return the parent vlab id for a project from the DB, or `None`
        if the project does not exist (or is soft-deleted)."""
        vlab_id = await session.scalar(
            select(Project.virtual_lab_id).where(
                Project.id == project_id,
                Project.deleted.is_(False),
            )
        )
        return vlab_id


project_admin = ProjectGate(role="admin")
project_access = ProjectGate(role="any")
workspace_access = ProjectGate(role="any", include_vlab_admin=True)
