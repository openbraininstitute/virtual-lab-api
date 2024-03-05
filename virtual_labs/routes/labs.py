from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.orm import Session

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.domain.labs import (
    LabResponse,
    VirtualLabDomain,
    VirtualLabCreate,
    VirtualLabUpdate,
)
from virtual_labs.usecases import labs as usecases

router = APIRouter(prefix="/virtual-labs")


@router.get("", response_model=LabResponse[list[VirtualLabDomain]])
def get_all_virtual_labs_for_user(
    db: Session = Depends(default_session_factory),
) -> LabResponse[list[VirtualLabDomain]]:
    all_labs = [
        VirtualLabDomain.model_validate(lab) for lab in usecases.all_labs_for_user(db)
    ]

    return LabResponse[list[VirtualLabDomain]](
        message="All virtual labs for user", data=all_labs
    )


@router.get("/{lab_id}", response_model=LabResponse[VirtualLabDomain])
def get_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> LabResponse[VirtualLabDomain]:
    lab = VirtualLabDomain.model_validate(usecases.get_virtual_lab(db, lab_id))
    return LabResponse[VirtualLabDomain](
        message="Virtual lab resource for id {}".format(lab_id),
        data=lab,
    )


@router.post("", response_model=LabResponse[VirtualLabDomain])
def create_virtual_lab(
    lab: VirtualLabCreate, db: Session = Depends(default_session_factory)
) -> LabResponse[VirtualLabDomain]:
    created_lab = VirtualLabDomain.model_validate(usecases.create_virtual_lab(db, lab))
    return LabResponse[VirtualLabDomain](
        message="Newly created virtual lab", data=created_lab
    )


@router.patch("/{lab_id}", response_model=LabResponse[VirtualLabDomain])
def update_virtual_lab(
    lab_id: UUID4,
    lab: VirtualLabUpdate,
    db: Session = Depends(default_session_factory),
) -> LabResponse[VirtualLabDomain]:
    udpated_lab = VirtualLabDomain.model_validate(
        usecases.update_virtual_lab(db, lab_id, lab)
    )
    return LabResponse[VirtualLabDomain](
        message="Updated virtual lab", data=udpated_lab
    )


@router.delete("/{lab_id}", response_model=LabResponse[VirtualLabDomain])
def delete_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> LabResponse[VirtualLabDomain]:
    deleted_lab = VirtualLabDomain.model_validate(
        usecases.delete_virtual_lab(db, lab_id)
    )
    return LabResponse[VirtualLabDomain](
        message="Deleted virtual lab", data=deleted_lab
    )
