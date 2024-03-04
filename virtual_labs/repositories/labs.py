from typing import List
from pydantic import UUID4
from sqlalchemy.orm import Session
import uuid

from virtual_labs.domain import labs
from virtual_labs.infrastructure.db.models import VirtualLab


def get_all_virtual_lab_for_user(db: Session) -> List[VirtualLab]:
    return db.query(VirtualLab).all()


def get_virtual_lab(db: Session, lab_id: UUID4) -> VirtualLab | None:
    return db.query(VirtualLab).filter(VirtualLab.id == lab_id).first()


def create_virtual_lab(db: Session, lab: labs.VirtualLabCreate) -> VirtualLab:
    db_lab = VirtualLab(
        name=lab.name,
        description=lab.description,
        reference_email=lab.reference_email,
        nexus_organization_id=uuid.uuid4(),
        projects=[],
    )

    db.add(db_lab)
    db.commit()
    db.refresh(db_lab)

    return db_lab
