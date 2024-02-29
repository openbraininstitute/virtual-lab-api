from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.orm import Session

from ..infrastructure.db.config import default_session_factory

router = APIRouter(prefix="/projects")


"""
    this is just an example how we should pass the db pool to the route as dependency injection
    it will be consumed by the service or the use case (if no validation)
"""


@router.get("/{project_id}")
def retrieve_project(db: Session = Depends(default_session_factory)) -> None:
    return
