from sqlalchemy.orm import Session
from typing_extensions import TypedDict

from virtual_labs.repositories import labs as repository

LabExists = TypedDict("LabExists", {"exists": bool})


def check_virtual_lab_name_exists(db: Session, name: str) -> LabExists:
    if name.strip() == "":
        return {"exists": True}
    return {"exists": repository.count_virtual_labs_with_name(db, name) > 0}
