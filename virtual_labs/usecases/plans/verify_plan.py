from sqlalchemy.orm import Session
from virtual_labs.repositories import plans
from sqlalchemy.exc import NoResultFound


def verify_plan(db: Session, plan_id: int) -> None:
    try:
        plans.get_plan(db, plan_id)
    except NoResultFound:
        raise ValueError("Plan with id {} does not exist".format(plan_id))
