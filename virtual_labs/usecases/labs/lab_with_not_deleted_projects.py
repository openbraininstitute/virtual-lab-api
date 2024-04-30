from datetime import datetime
from typing import Optional

from pydantic import UUID4, BaseModel

from virtual_labs.domain.labs import (
    VirtualLabDomain,
    VirtualLabDomainVerbose,
    VirtualLabProjectOut,
)
from virtual_labs.domain.project import ProjectStar
from virtual_labs.infrastructure.db import models


class VirtualLabProject(BaseModel):
    id: UUID4
    name: str
    description: str | None
    project_stars: list[ProjectStar] | None = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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


def to_project_out(project: ProjectVerbose, user_id: UUID4) -> VirtualLabProjectOut:
    if project.project_stars is None:
        return VirtualLabProjectOut(**project.model_dump(), starred=False)

    project_stars_users = [star.user_id for star in project.project_stars]
    return VirtualLabProjectOut(
        **project.model_dump(), starred=user_id in project_stars_users
    )


def lab_with_not_deleted_projects(
    lab: models.VirtualLab, user_id: UUID4
) -> VirtualLabDomainVerbose:
    domain_lab = VirtualLabWithProjectVerbose.model_validate(lab)
    all_projects = domain_lab.projects if domain_lab.projects is not None else []

    non_deleted_projects = [
        to_project_out(project, user_id)
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
        entity=domain_lab.entity,
    )
