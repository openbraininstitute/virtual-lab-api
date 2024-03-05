from typing import List

from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from sqlalchemy.orm import Session


def all_labs_for_user(db: Session) -> List[models.VirtualLab]:
    # TODO: Use keycloak to retrieve only labs that belong to the current user
    return repository.get_all_virtual_lab_for_user(db)
