from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.orm import Session

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.common import PageParams, PaginatedResultsResponse
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
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.usecases import labs as usecases
from virtual_labs.usecases.labs.check_virtual_lab_name_exists import LabExists

PaginatedLabs = LabResponse[PaginatedResultsResponse[VirtualLabWithProject]]
router = APIRouter(prefix="/virtual-labs", tags=["Virtual Labs Endpoints"])


@router.get("", response_model=PaginatedLabs)
def get_paginated_virtual_labs_for_user(
    page: int = 1,
    size: int = 50,
    db: Session = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> PaginatedLabs:
    return LabResponse(
        message="Paginated virtual labs for user",
        data=usecases.paginated_labs_for_user(
            db,
            page_params=PageParams(page=page, size=size),
            user_id=get_user_id_from_auth(auth),
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
        data=usecases.search_virtual_labs_by_name(q, db),
    )


@router.get(
    "/{lab_id}",
    response_model=LabResponse[LabVerbose],
    summary="Get non deleted virtual lab by id",
)
async def get_virtual_lab(
    lab_id: UUID4,
    db: Session = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[LabVerbose]:
    lab_response = LabVerbose(
        virtual_lab=await usecases.get_virtual_lab(
            db, lab_id, user_id=get_user_id_from_auth(auth)
        )
    )
    return LabResponse[LabVerbose](
        message="Virtual lab resource for id {}".format(lab_id),
        data=lab_response,
    )


@router.get("/{lab_id}/users", response_model=LabResponse[VirtualLabUsers])
async def get_virtual_lab_users(
    lab_id: UUID4,
    db: Session = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[VirtualLabUsers]:
    return LabResponse[VirtualLabUsers](
        message="Users for virtual lab",
        data=usecases.get_virtual_lab_users(
            db, lab_id, user_id=get_user_id_from_auth(auth)
        ),
    )


@router.post("", response_model=LabResponse[Lab])
async def create_virtual_lab(
    lab: VirtualLabCreate,
    db: Session = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[Lab]:
    created_lab = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            await usecases.create_virtual_lab(db, lab, auth=auth)
        )
    )

    return LabResponse[Lab](message="Newly created virtual lab", data=created_lab)


@router.patch("/{lab_id}", response_model=LabResponse[Lab])
def update_virtual_lab(
    lab_id: UUID4,
    lab: VirtualLabUpdate,
    db: Session = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[Lab]:
    udpated_lab = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            usecases.update_virtual_lab(
                db, lab_id, user_id=get_user_id_from_auth(auth), lab=lab
            )
        )
    )
    return LabResponse[Lab](message="Updated virtual lab", data=udpated_lab)


@router.post(
    "/{lab_id}/users",
    summary="Invite user to lab by email",
    response_model=LabResponse[InviteSent],
    tags=["Not Yet Implemented"],
)
async def invite_user_to_virtual_lab(
    lab_id: UUID4,
    invite_details: AddUserToVirtualLab,
    db: Session = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[InviteSent]:
    invite_id = await usecases.invite_user_to_lab(
        lab_id,
        inviter_id=get_user_id_from_auth(auth),
        invite_details=invite_details,
        db=db,
    )
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
    user_id: UUID4,
    new_role: UserRoleEnum,
    db: Session = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[VirtualLabUser]:
    return usecases.change_user_role_for_lab(
        lab_id,
        user_making_change_id=get_user_id_from_auth(auth),
        user_id=user_id,
        new_role=new_role,
        db=db,
    )


@router.delete(
    "/{lab_id}/users/{user_id}",
    response_model=LabResponse[None],
)
def remove_user_from_virtual_lab(
    lab_id: UUID4,
    user_id: UUID4,
    db: Session = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[None]:
    usecases.remove_user_from_lab(
        lab_id, user_making_change=get_user_id_from_auth(auth), user_id=user_id, db=db
    )
    return LabResponse[None](message="User removed from virtual lab", data=None)


@router.delete("/{lab_id}", response_model=LabResponse[Lab])
async def delete_virtual_lab(
    lab_id: UUID4,
    db: Session = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[Lab]:
    deleted_lab = Lab(
        virtual_lab=VirtualLabDomain.model_validate(
            await usecases.delete_virtual_lab(db, lab_id, auth=auth)
        )
    )
    return LabResponse[Lab](message="Deleted virtual lab", data=deleted_lab)
