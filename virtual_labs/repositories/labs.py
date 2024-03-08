from typing import List
from pydantic import UUID4
from sqlalchemy.orm import Session
import uuid
from sqlalchemy.sql import func
from virtual_labs.domain import labs
from virtual_labs.infrastructure.db.models import VirtualLab


def get_all_virtual_lab_for_user(db: Session) -> List[VirtualLab]:
    return db.query(VirtualLab).all()


def get_virtual_lab(db: Session, lab_id: UUID4) -> VirtualLab:
    return db.query(VirtualLab).filter(VirtualLab.id == lab_id).one()


def create_virtual_lab(db: Session, lab: labs.VirtualLabCreate) -> VirtualLab:
    db_lab = VirtualLab(
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
    query = db.query(VirtualLab).filter(VirtualLab.id == lab_id)
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
    db.delete(lab)
    db.commit()
    return lab
