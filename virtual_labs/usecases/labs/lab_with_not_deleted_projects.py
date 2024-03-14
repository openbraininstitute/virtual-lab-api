from datetime import datetime
from typing import Optional

from virtual_labs.domain.labs import (
    VirtualLabDomain,
    VirtualLabDomainVerbose,
    VirtualLabProject,
)
from virtual_labs.infrastructure.db import models


class ProjectVerbose(VirtualLabProject):
    deleted: bool

    class Config:
        from_attributes = True


class VirtualLabWithProjectVerbose(VirtualLabDomain):
    nexus_organization_id: str
    deleted: bool

    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    projects: list[ProjectVerbose] | None

    class Config:
        from_attributes = True


def lab_with_not_deleted_projects(lab: models.VirtualLab) -> VirtualLabDomainVerbose:
    domain_lab = VirtualLabWithProjectVerbose.model_validate(lab)
    all_projects = domain_lab.projects if domain_lab.projects is not None else []

    non_deleted_projects = [
        VirtualLabProject.model_validate(project)
        for project in all_projects
        if not project.deleted
    ]
    return VirtualLabDomainVerbose(
        projects=non_deleted_projects,
        name=domain_lab.name,
        description=domain_lab.description,
        reference_email=domain_lab.reference_email,
        budget=domain_lab.budget,
        id=domain_lab.id,
        plan_id=domain_lab.plan_id,
        created_at=domain_lab.created_at,
        nexus_organization_id=domain_lab.nexus_organization_id,
        deleted=domain_lab.deleted,
        deleted_at=domain_lab.deleted_at,
        updated_at=domain_lab.updated_at,
    )
