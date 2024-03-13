import uuid
from typing import List

from pydantic import UUID4
from sqlalchemy import func
from sqlalchemy.orm import Session

from virtual_labs.domain import labs
from virtual_labs.domain.common import PageParams
from virtual_labs.infrastructure.db.models import Project, VirtualLab


class VirtualLabDbCreate(labs.VirtualLabCreate):
    id: UUID4
    admin_group_id: str
    member_group_id: str


def get_all_virtual_lab_for_user(db: Session) -> List[VirtualLab]:
    return db.query(VirtualLab).filter(~VirtualLab.deleted).all()


def get_paginated_virtual_labs(
    db: Session, page_params: PageParams
) -> list[VirtualLab]:
    paginated_query = (
        db.query(VirtualLab)
        .filter(~VirtualLab.deleted)
        .offset((page_params.page - 1) * page_params.size)
        .limit(page_params.size)
        .all()
    )

    return paginated_query


def get_virtual_lab(db: Session, lab_id: UUID4) -> VirtualLab:
    return (
        db.query(VirtualLab).filter(~VirtualLab.deleted, VirtualLab.id == lab_id).one()
    )


def create_virtual_lab(db: Session, lab: VirtualLabDbCreate) -> VirtualLab:
    db_lab = VirtualLab(
        id=lab.id,
        admin_group_id=lab.admin_group_id,
        member_group_id=lab.member_group_id,
        name=lab.name,
        description=lab.description,
        reference_email=lab.reference_email,
        nexus_organization_id=uuid.uuid4(),
        projects=[],
        budget=lab.budget,
        plan_id=lab.plan_id,
    )

    db.add(db_lab)
    db.commit()

    return db_lab


def update_virtual_lab(
    db: Session, lab_id: UUID4, lab: labs.VirtualLabUpdate
) -> VirtualLab:
    query = db.query(VirtualLab).filter(~VirtualLab.deleted, VirtualLab.id == lab_id)
    current = query.one()

    data_to_update = lab.model_dump(exclude_unset=True)
    query.update(
        {
            "name": data_to_update.get("name", current.name),
            "description": data_to_update.get("description", current.description),
            "reference_email": data_to_update.get(
                "reference_email", current.reference_email
            ),
            "updated_at": func.now(),
            "budget": data_to_update.get("budget", current.budget),
            "plan_id": data_to_update.get("plan_id", current.plan_id),
        }
    )
    db.commit()
    return current


def delete_virtual_lab(db: Session, lab_id: UUID4) -> VirtualLab:
    lab = get_virtual_lab(db, lab_id)
    now = func.now()

    # Mark virtual lab as deleted
    db.query(VirtualLab).where(VirtualLab.id == lab_id).update(
        {"deleted": True, "deleted_at": now}
    )

    # Mark projects for the virtual lab as deleted
    db.query(Project).where(Project.virtual_lab_id == lab_id).update(
        {"deleted": True, "deleted_at": now}
    )

    db.commit()
    return lab


def count_virtual_labs_with_name(db: Session, name: str) -> int:
    return (
        db.query(VirtualLab)
        .filter(~VirtualLab.deleted, func.lower(VirtualLab.name) == func.lower(name))
        .count()
    )


def get_virtual_labs_with_matching_name(db: Session, term: str) -> list[VirtualLab]:
    return (
        db.query(VirtualLab)
        .filter(
            ~VirtualLab.deleted,
            func.lower(VirtualLab.name).like(f"%{term.strip().lower()}%"),
        )
        .all()
    )
