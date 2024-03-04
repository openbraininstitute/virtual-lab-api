from sqlalchemy.orm import Session
import uuid

from virtual_labs.domain import labs
from virtual_labs.infrastructure.db.models import VirtualLab


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
