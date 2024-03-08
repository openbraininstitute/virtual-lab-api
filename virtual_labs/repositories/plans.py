from sqlalchemy.orm import Session
from virtual_labs.infrastructure.db.models import Plan


def get_plan(db: Session, plan_id: int) -> Plan:
    return db.query(Plan).filter(Plan.id == plan_id).one()


def get_all_plans(db: Session) -> list[Plan]:
    return db.query(Plan).all()
