from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.orm import Session

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.domain.labs import (
    AllLabs,
    Lab,
    LabResponse,
    VirtualLabDomain,
    VirtualLabCreate,
    VirtualLabUpdate,
)
from virtual_labs.usecases import labs as usecases

router = APIRouter(prefix="/virtual-labs")


@router.get("", response_model=LabResponse[AllLabs])
def get_all_virtual_labs_for_user(
    db: Session = Depends(default_session_factory),
) -> LabResponse[AllLabs]:
    all_labs = [
        VirtualLabDomain.model_validate(lab) for lab in usecases.all_labs_for_user(db)
    ]
    response = AllLabs(all_virtual_labs=all_labs)
    return LabResponse[AllLabs](message="All virtual labs for user", data=response)


@router.get("/{lab_id}", response_model=LabResponse[Lab])
def get_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> LabResponse[Lab]:
    lab_response = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            usecases.get_virtual_lab(db, lab_id)
        )
    )
    return LabResponse[Lab](
        message="Virtual lab resource for id {}".format(lab_id),
        data=lab_response,
    )


@router.post("", response_model=LabResponse[Lab])
def create_virtual_lab(
    lab: VirtualLabCreate, db: Session = Depends(default_session_factory)
) -> LabResponse[Lab]:
    created_lab = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            usecases.create_virtual_lab(db, lab)
        )
    )

    return LabResponse[Lab](message="Newly created virtual lab", data=created_lab)


@router.patch("/{lab_id}", response_model=LabResponse[Lab])
def update_virtual_lab(
    lab_id: UUID4,
    lab: VirtualLabUpdate,
    db: Session = Depends(default_session_factory),
) -> LabResponse[Lab]:
    udpated_lab = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            usecases.update_virtual_lab(db, lab_id, lab)
        )
    )
    return LabResponse[Lab](message="Updated virtual lab", data=udpated_lab)


@router.delete("/{lab_id}", response_model=LabResponse[Lab])
def delete_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> LabResponse[Lab]:
    deleted_lab = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            usecases.delete_virtual_lab(db, lab_id)
        )
    )
    return LabResponse[Lab](message="Deleted virtual lab", data=deleted_lab)
