import uuid
from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.orm import Session

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.domain.labs import (
    LabVerbose,
    Labs,
    Lab,
    LabResponse,
    VirtualLabDomain,
    VirtualLabDomainVerbose,
    VirtualLabCreate,
    VirtualLabUpdate,
    VirtualLabWithProject,
)
from virtual_labs.usecases import labs as usecases
from virtual_labs.usecases.labs.check_virtual_lab_name_exists import LabExists

router = APIRouter(prefix="/virtual-labs", tags=["Virtual Labs Endpoints"])


@router.get("", response_model=LabResponse[Labs])
def get_all_virtual_labs_for_user(
    db: Session = Depends(default_session_factory),
) -> LabResponse[Labs]:
    all_labs = [
        VirtualLabWithProject.model_validate(lab)
        for lab in usecases.all_labs_for_user(db)
    ]
    response = Labs(virtual_labs=all_labs)
    return LabResponse[Labs](message="All virtual labs for user", data=response)


@router.get("/_check", response_model=LabResponse[LabExists])
def check_if_virtual_lab_name_exists(
    q: str, db: Session = Depends(default_session_factory)
) -> LabResponse[LabExists]:
    response = usecases.check_virtual_lab_name_exists(db, q)
    return LabResponse[LabExists](
        message=f"Virtual lab with name {q} already exists"
        if response["exists"] > 0
        else f"No virtual lab with name {q} was found",
        data=response,
    )


@router.get("/_search", response_model=LabResponse[Labs])
def search_virtual_lab_by_name(
    q: str, db: Session = Depends(default_session_factory)
) -> LabResponse[Labs]:
    return LabResponse[Labs](
        message=f"All labs with names matching {q} for user",
        data=usecases.search_virtual_labs_by_name(q, uuid.uuid4(), db),
    )


@router.get(
    "/{lab_id}",
    response_model=LabResponse[LabVerbose],
    summary="Get non deleted virtual lab by id",
)
def get_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> LabResponse[LabVerbose]:
    lab_response = LabVerbose(
        virtual_lab=VirtualLabDomainVerbose.model_validate(
            usecases.get_virtual_lab(db, lab_id)
        )
    )
    return LabResponse[LabVerbose](
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
