from typing import List
from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.orm import Session

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db import models
from virtual_labs.domain import labs as domains
from virtual_labs.usecases import labs as usecases

router = APIRouter(prefix="/virtual-labs")


@router.get("", response_model=list[domains.VirtualLab])
def get_all_virtual_labs_for_user(
    db: Session = Depends(default_session_factory),
) -> List[models.VirtualLab]:
    return usecases.all_labs_for_user(db)


@router.get("/{lab_id}", response_model=domains.VirtualLab)
def get_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> models.VirtualLab:
    return usecases.get_virtual_lab(db, lab_id)


@router.post("", response_model=domains.VirtualLab)
def create_virtual_lab(
    lab: domains.VirtualLabCreate, db: Session = Depends(default_session_factory)
) -> models.VirtualLab:
    return usecases.create_virtual_lab(db, lab)


@router.patch("/{lab_id}", response_model=domains.VirtualLab)
def update_virtual_lab(
    lab_id: UUID4,
    lab: domains.VirtualLabUpdate,
    db: Session = Depends(default_session_factory),
) -> models.VirtualLab:
    return usecases.update_virtual_lab(db, lab_id, lab)


@router.delete("/{lab_id}", response_model=domains.VirtualLab)
def delete_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> models.VirtualLab:
    return usecases.delete_virtual_lab(db, lab_id)
