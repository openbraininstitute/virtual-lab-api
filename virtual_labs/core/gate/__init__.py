"""Lightweight FastAPI-dependency authorization gates.

Replaces the legacy `core.authorization` decorators with small,
typed, composable dependencies that read the requester's structured
`Grants` view (populated once per request by `parse_auth_grants`)
instead of round-tripping Keycloak.

Quick reference:

    from virtual_labs.core.gate import (
        vlab_admin, vlab_access,
        project_admin, project_access, workspace_access,
        ServiceGate,
    )

    # Vlab — `virtual_lab_id` comes from the path.
    @router.post("/virtual-labs/{virtual_lab_id}/projects")
    async def create_project(
        virtual_lab_id: UUID,
        user: AuthUserGrants = Depends(vlab_admin),
    ): ...

    # Project — `project_id` comes from the path. The `_or_vlab`
    # variant also lets admins of the parent vlab through.
    @router.get("/projects/{project_id}")
    async def read_project(
        project_id: UUID,
        user: AuthUserGrants = Depends(workspace_access),
    ): ...

    # Service — service name is fixed at construction time.
    @router.post(
        "/admin/entitycore/...",
        dependencies=[Depends(ServiceGate("entitycore"))],
    )
    async def admin_endpoint(): ...

Migration from `core.authorization`:

    @verify_vlab_write          ->  Depends(vlab_admin)
    @verify_vlab_read           ->  Depends(vlab_access)
    @verify_project_write       ->  Depends(project_admin)
    @verify_project_read        ->  Depends(project_access)
    verify_vlab_or_project_read_dep
                                ->  Depends(workspace_access)
    @verify_service_admin([...])
                                ->  Depends(ServiceGate(name))
"""

from virtual_labs.core.gate.base import forbidden
from virtual_labs.core.gate.project import (
    ProjectGate,
    ProjectRole,
    project_access,
    project_admin,
    workspace_access,
)
from virtual_labs.core.gate.service import ServiceGate
from virtual_labs.core.gate.vlab import (
    VirtualLabGate,
    VlabRole,
    virtuallab_access,
    virtuallab_admin,
)

__all__ = [
    "forbidden",
    # vlab
    "VirtualLabGate",
    "VlabRole",
    "virtuallab_admin",
    "virtuallab_access",
    # project
    "ProjectGate",
    "ProjectRole",
    "project_admin",
    "project_access",
    "workspace_access",
    # service
    "ServiceGate",
]
