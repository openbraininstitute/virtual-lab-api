from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from sqlalchemy.orm import Session


class VirtualLabService:
    def create_virtual_lab(
        self, db: Session, lab: domain.VirtualLabCreate
    ) -> models.VirtualLab:
        return repository.create_virtual_lab(db, lab)
