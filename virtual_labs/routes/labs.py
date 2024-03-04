from http import HTTPStatus
from typing import List
from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.orm import Session
from virtual_labs.core.exceptions.api_error import VlmError, VlmErrorCode

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db import models
from virtual_labs.services.labs import VirtualLabService
from virtual_labs.domain import labs as domains

router = APIRouter(prefix="/virtual-labs")

virtual_lab_service = VirtualLabService()


@router.get("", response_model=List[domains.VirtualLab])
def get_all_virtual_labs_for_user(
    db: Session = Depends(default_session_factory),
) -> list[models.VirtualLab]:
    return virtual_lab_service.get_all_virtual_labs_for_user(db)


@router.get("/{lab_id}", response_model=domains.VirtualLab)
def get_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> models.VirtualLab:
    lab = virtual_lab_service.get_virtual_lab(db, lab_id)
    if lab is None:
        raise VlmError(
            message="Virtual lab not found",
            error_code=VlmErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    return lab


@router.post("", response_model=domains.VirtualLab)
def create_virtual_lab(
    lab: domains.VirtualLabCreate, db: Session = Depends(default_session_factory)
) -> models.VirtualLab:
    return virtual_lab_service.create_virtual_lab(db, lab)


@router.patch("/{lab_id}", response_model=domains.VirtualLab)
def update_virtual_lab(
    lab_id: UUID4,
    lab: domains.VirtualLabUpdate,
    db: Session = Depends(default_session_factory),
) -> models.VirtualLab:
    updated_lab = virtual_lab_service.update_virtual_lab(db, lab_id, lab)
    if updated_lab is None:
        raise VlmError(
            message="Virtual lab not found",
            error_code=VlmErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    return updated_lab


@router.delete("/{lab_id}", response_model=domains.VirtualLab)
def delete_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> models.VirtualLab:
    deleted_lab = virtual_lab_service.delete_virtual_lab(db, lab_id)
    if deleted_lab is None:
        raise VlmError(
            message="Virtual lab not found",
            error_code=VlmErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    return deleted_lab
