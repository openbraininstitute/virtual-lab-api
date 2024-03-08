from sqlalchemy.orm import Session
from virtual_labs.infrastructure.db.models import Plan
from virtual_labs.repositories import plans


def all_plans(db: Session) -> list[Plan]:
    return plans.get_all_plans(db)
