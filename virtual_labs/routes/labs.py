import uuid

from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.orm import Session

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.common import PagedResponse, PageParams
from virtual_labs.domain.labs import (
    AddUserToVirtualLab,
    InviteSent,
    Lab,
    LabResponse,
    Labs,
    LabVerbose,
    VirtualLabCreate,
    VirtualLabDomain,
    VirtualLabUpdate,
    VirtualLabUser,
    VirtualLabUsers,
    VirtualLabWithProject,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.usecases import labs as usecases
from virtual_labs.usecases.labs.check_virtual_lab_name_exists import LabExists

PaginatedLabs = LabResponse[PagedResponse[VirtualLabWithProject]]
router = APIRouter(prefix="/virtual-labs", tags=["Virtual Labs Endpoints"])


# TODO: Remove this and retrieve user from session
def get_test_user_id() -> UUID4:
    """Returns uuid of the test user created in keycloak."""
    return uuid.UUID("b7ceda53-625c-41ba-bce0-8c1e51bfaec7")


@router.get("", response_model=PaginatedLabs)
def get_paginated_virtual_labs_for_user(
    page: int = 1, size: int = 50, db: Session = Depends(default_session_factory)
) -> PaginatedLabs:
    user_id = get_test_user_id()
    return LabResponse(
        message="Paginated virtual labs for user",
        data=usecases.paginated_labs_for_user(
            db, page_params=PageParams(page=page, size=size), user_id=user_id
        ),
    )


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
    user_id = get_test_user_id()
    lab_response = LabVerbose(virtual_lab=usecases.get_virtual_lab(db, lab_id, user_id))
    return LabResponse[LabVerbose](
        message="Virtual lab resource for id {}".format(lab_id),
        data=lab_response,
    )


@router.get("/{lab_id}/users", response_model=LabResponse[VirtualLabUsers])
async def get_virtual_lab_users(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> LabResponse[VirtualLabUsers]:
    user_id = get_test_user_id()
    return LabResponse[VirtualLabUsers](
        message="Users for virtual lab",
        data=usecases.get_virtual_lab_users(db, lab_id, user_id),
    )


@router.post("", response_model=LabResponse[Lab])
async def create_virtual_lab(
    lab: VirtualLabCreate, db: Session = Depends(default_session_factory)
) -> LabResponse[Lab]:
    owner_id = get_test_user_id()
    created_lab = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            await usecases.create_virtual_lab(db, lab, owner_id)
        )
    )

    return LabResponse[Lab](message="Newly created virtual lab", data=created_lab)


@router.patch("/{lab_id}", response_model=LabResponse[Lab])
def update_virtual_lab(
    lab_id: UUID4,
    lab: VirtualLabUpdate,
    db: Session = Depends(default_session_factory),
) -> LabResponse[Lab]:
    user_id = get_test_user_id()
    udpated_lab = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            usecases.update_virtual_lab(db, lab_id, user_id, lab)
        )
    )
    return LabResponse[Lab](message="Updated virtual lab", data=udpated_lab)


@router.post(
    "/{lab_id}/users",
    summary="Invite user to lab by email",
    response_model=LabResponse[InviteSent],
)
def invite_user_to_virtual_lab(
    lab_id: UUID4,
    invite_details: AddUserToVirtualLab,
    db: Session = Depends(default_session_factory),
) -> LabResponse[InviteSent]:
    inviter_id = get_test_user_id()
    invite_id = usecases.invite_user_to_lab(lab_id, inviter_id, invite_details, db)
    return LabResponse[InviteSent](
        message="Invite sent to user", data=InviteSent(invite_id=invite_id)
    )


@router.post(
    "/{lab_id}/accept-invite/{invite_id}",
    tags=["Not Yet Implemented"],
    summary="Accept invite to virtual lab",
)
def accept_invite_to_lab(
    invite_id: UUID4,
    user_id: UUID4,
    db: Session = Depends(default_session_factory),
) -> LabResponse[None]:
    usecases.accept_invite(invite_id=invite_id, user_id=user_id, db=db)
    return LabResponse[None](
        message="Invitation to virtual lab successfully accepted", data=None
    )


@router.patch(
    "/{lab_id}/users/{user_id}",
    response_model=LabResponse[VirtualLabUser],
)
def change_user_role_for_lab(
    lab_id: UUID4,
    user_id: UUID4,  # TODO: user_id should be retrieved from invite link
    new_role: UserRoleEnum,
    db: Session = Depends(default_session_factory),
) -> LabResponse[VirtualLabUser]:
    user_making_change_id = get_test_user_id()
    return usecases.change_user_role_for_lab(
        lab_id, user_making_change_id, user_id, new_role, db
    )


@router.delete(
    "/{lab_id}/users/{user_id}",
    response_model=LabResponse[None],
)
def remove_user_from_virtual_lab(
    lab_id: UUID4, user_id: UUID4, db: Session = Depends(default_session_factory)
) -> LabResponse[None]:
    user_making_change_id = get_test_user_id()
    usecases.remove_user_from_lab(lab_id, user_making_change_id, user_id, db)
    return LabResponse[None](message="User removed from virtual lab", data=None)


@router.delete("/{lab_id}", response_model=LabResponse[Lab])
def delete_virtual_lab(
    lab_id: UUID4, db: Session = Depends(default_session_factory)
) -> LabResponse[Lab]:
    user_id = get_test_user_id()
    deleted_lab = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            usecases.delete_virtual_lab(db, lab_id, user_id)
        )
    )
    return LabResponse[Lab](message="Deleted virtual lab", data=deleted_lab)
