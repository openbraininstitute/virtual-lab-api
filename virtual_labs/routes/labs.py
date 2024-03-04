from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.services.labs import VirtualLabService
from virtual_labs.domain import labs as domains

router = APIRouter(prefix="/virtual-labs")

virtual_lab_service = VirtualLabService()


@router.post("", response_model=domains.VirtualLab)
def create_virtual_lab(
    lab: domains.VirtualLabCreate, db: Session = Depends(default_session_factory)
) -> VirtualLab:
    return virtual_lab_service.create_virtual_lab(db, lab)
