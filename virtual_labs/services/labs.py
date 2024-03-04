from typing import List

from pydantic import UUID4
from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from sqlalchemy.orm import Session


class VirtualLabService:
    def get_all_virtual_labs_for_user(self, db: Session) -> List[models.VirtualLab]:
        # TODO: Use keycloak to retrieve only labs that belong to the current user
        return repository.get_all_virtual_lab_for_user(db)

    def get_virtual_lab(self, db: Session, lab_id: UUID4) -> models.VirtualLab | None:
        return repository.get_virtual_lab(db, lab_id)

    def create_virtual_lab(
        self, db: Session, lab: domain.VirtualLabCreate
    ) -> models.VirtualLab:
        return repository.create_virtual_lab(db, lab)

    def update_virtual_lab(
        self, db: Session, lab_id: UUID4, lab: domain.VirtualLabUpdate
    ) -> models.VirtualLab | None:
        return repository.update_virtual_lab(db, lab_id, lab)

    def delete_virtual_lab(
        self, db: Session, lab_id: UUID4
    ) -> models.VirtualLab | None:
        return repository.delete_virtual_lab(db, lab_id)
