from typing import Annotated, Dict, List, Tuple

from fastapi import APIRouter, Body, Depends, Response
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import (
    verify_user_authenticated,
    verify_vlab_read,
    verify_vlab_write,
    verity_member_invite,
)
from virtual_labs.core.types import UserGroup, UserRoleEnum, VliAppResponse
from virtual_labs.domain.common import VirtualLabResponse
from virtual_labs.domain.email import (
    EmailVerificationPayload,
    InitiateEmailVerificationPayload,
    VerificationCodeEmailResponse,
)
from virtual_labs.domain.invite import (
    AddUser,
    DeleteLabInviteRequest,
)
from virtual_labs.domain.labs import (
    CreateLabOut,
    InviteSent,
    LabResponse,
    SearchLabResponse,
    VirtualLabCreate,
    VirtualLabDetails,
    VirtualLabOut,
    VirtualLabStats,
    VirtualLabUpdate,
    VirtualLabUser,
    VirtualLabUsers,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import a_verify_jwt, verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.redis.email_rate_limit import (
    rate_limit_initiate,
    rate_limit_verify,
)
from virtual_labs.infrastructure.redis.rate_limiter import RateLimiter, get_rate_limiter
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.usecases import email_verification as email_verification_usecases
from virtual_labs.usecases import labs as usecases
from virtual_labs.usecases.labs.check_virtual_lab_name_exists import LabExists

PaginatedLabs = LabResponse[VirtualLabResponse[VirtualLabDetails]]
router = APIRouter(prefix="/virtual-labs", tags=["Virtual Labs Endpoints"])


@router.get("", response_model=LabResponse[VirtualLabResponse[VirtualLabDetails]])
@verify_user_authenticated
async def get_paginated_virtual_labs_for_user(
    db: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> LabResponse[VirtualLabResponse[VirtualLabDetails | None]]:
    return LabResponse(
        message="List of user virtual lab and pending labs from invites",
        data=await usecases.list_user_virtual_labs(
            db,
            auth=auth,
        ),
    )


@router.get("/_check", response_model=LabResponse[LabExists])
async def check_if_virtual_lab_name_exists(
    q: str, db: AsyncSession = Depends(default_session_factory)
) -> LabResponse[LabExists]:
    response = await usecases.check_virtual_lab_name_exists(db, q)
    return LabResponse[LabExists](
        message=f"Virtual lab with name {q} already exists"
        if response["exists"] > 0
        else f"No virtual lab with name {q} was found",
        data=response,
    )


@router.get(
    "/_search",
    response_model=LabResponse[SearchLabResponse],
    description="Search virtual labs that user is a member of, by lab name",
)
async def search_virtual_lab_by_name(
    q: str,
    db: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[SearchLabResponse]:
    return LabResponse[SearchLabResponse](
        message=f"All labs with names matching {q} for user",
        data=await usecases.search_virtual_labs_by_name(
            q, db, get_user_id_from_auth(auth)
        ),
    )


@router.get(
    "/{virtual_lab_id}",
    response_model=LabResponse[VirtualLabOut],
    summary="Get non deleted virtual lab by id",
)
@verify_vlab_read
async def get_virtual_lab(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[VirtualLabOut]:
    lab_response = await usecases.get_virtual_lab(
        session, virtual_lab_id, user_id=get_user_id_from_auth(auth)
    )
    return LabResponse[VirtualLabOut](
        message="Virtual lab resource for id {}".format(virtual_lab_id),
        data=lab_response,
    )


@router.get(
    "/{virtual_lab_id}/stats",
    response_model=LabResponse[VirtualLabStats],
    summary="Get statistics for a virtual lab",
)
@verify_vlab_read
async def get_virtual_lab_stats(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[VirtualLabStats]:
    stats = await usecases.get_virtual_lab_stats(session, virtual_lab_id)
    return LabResponse[VirtualLabStats](
        message="Statistics for virtual lab",
        data=stats,
    )


@router.get("/{virtual_lab_id}/users", response_model=LabResponse[VirtualLabUsers])
@verify_vlab_read
async def get_virtual_lab_users(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[VirtualLabUsers]:
    return LabResponse[VirtualLabUsers](
        message="Users for virtual lab",
        data=await usecases.get_virtual_lab_users(session, virtual_lab_id),
    )


@router.post("", response_model=LabResponse[CreateLabOut])
async def create_virtual_lab(
    lab: VirtualLabCreate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[CreateLabOut]:
    result = await usecases.create_virtual_lab(session, lab, auth)
    return LabResponse[CreateLabOut](message="Newly created virtual lab", data=result)


@router.post(
    "/email/initiate-verification",
    operation_id="initiate_email_verification",
    summary="initiate email verification",
    response_model=VliAppResponse[VerificationCodeEmailResponse],
)
async def initiate_email_verification(
    payload: InitiateEmailVerificationPayload,
    session: AsyncSession = Depends(default_session_factory),
    rl: RateLimiter = Depends(get_rate_limiter),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
    _: int | None = Depends(rate_limit_initiate),
) -> Response:
    return await email_verification_usecases.initiate_email_verification(
        session,
        rl,
        email=payload.email,
        virtual_lab_name=payload.name,
        auth=auth,
    )


@router.post(
    "/email/verify-code",
    operation_id="verify_code_email_verification",
    summary="finish email verification",
    response_model=VliAppResponse[VerificationCodeEmailResponse],
)
async def complete_email_verification(
    payload: EmailVerificationPayload,
    session: AsyncSession = Depends(default_session_factory),
    rl: RateLimiter = Depends(get_rate_limiter),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
    _: int | None = Depends(rate_limit_verify),
) -> Response:
    return await email_verification_usecases.verify_email_code(
        session,
        rl,
        email=payload.email,
        code=payload.code,
        virtual_lab_name=payload.name,
        auth=auth,
    )


@router.patch("/{virtual_lab_id}", response_model=LabResponse[VirtualLabOut])
@verify_vlab_write
async def update_virtual_lab(
    virtual_lab_id: UUID4,
    lab: VirtualLabUpdate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[VirtualLabOut]:
    updated_lab = await usecases.update_virtual_lab(
        session, virtual_lab_id, lab=lab, user_id=get_user_id_from_auth(auth)
    )
    return LabResponse[VirtualLabOut](message="Updated virtual lab", data=updated_lab)


@router.post(
    "/{virtual_lab_id}/invites",
    summary="Invite user to lab by email",
    response_model=LabResponse[InviteSent],
)
@verity_member_invite
async def invite_user_to_virtual_lab(
    virtual_lab_id: UUID4,
    invite_details: AddUser,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[InviteSent]:
    invite_id = await usecases.invite_user_to_lab(
        virtual_lab_id,
        inviter_id=get_user_id_from_auth(auth),
        invite_details=invite_details,
        db=session,
    )
    return LabResponse[InviteSent](
        message="Invite sent to user", data=InviteSent(invite_id=invite_id)
    )


@router.patch(
    "/{virtual_lab_id}/users/role",
    response_model=LabResponse[VirtualLabUser],
)
@verify_vlab_write
async def update_user_role_for_lab(
    virtual_lab_id: UUID4,
    user_id: Annotated[UUID4, Body(embed=True)],
    new_role: Annotated[UserRoleEnum, Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[VirtualLabUser]:
    return await usecases.change_user_role_for_lab(
        virtual_lab_id,
        user_id=user_id,
        new_role=new_role,
        db=session,
    )


@router.post(
    "/{virtual_lab_id}/users/detach",
    response_model=LabResponse[None],
)
@verify_vlab_write
async def remove_user_from_virtual_lab(
    virtual_lab_id: UUID4,
    user_id: Annotated[UUID4, Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[None]:
    await usecases.remove_user_from_lab(virtual_lab_id, user_id=user_id, db=session)
    return LabResponse[None](message="User removed from virtual lab", data=None)


@router.delete("/{virtual_lab_id}", response_model=LabResponse[VirtualLabOut])
@verify_vlab_write
async def delete_virtual_lab(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[VirtualLabOut]:
    deleted_lab = await usecases.delete_virtual_lab(session, virtual_lab_id, auth=auth)
    return LabResponse[VirtualLabOut](message="Deleted virtual lab", data=deleted_lab)


@router.post(
    "/{virtual_lab_id}/invites/cancel",
    response_model=LabResponse[None],
    description="Delete invite. Only invites that are not accepted can be deleted.",
)
@verify_vlab_write
async def delete_lab_invite(
    virtual_lab_id: UUID4,
    invite_details: DeleteLabInviteRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[None]:
    return await usecases.delete_lab_invite(
        session, virtual_lab_id, invite_details.email, invite_details.role
    )


@router.get(
    "/{virtual_lab_id}/user-groups",
    summary="Get user's groups for a virtual lab",
    description="Get the groups the authenticated user is a part of for the specified virtual lab (admin or member)",
    response_model=VliAppResponse[Dict[str, List[UserGroup]]],
)
async def get_user_groups_for_virtual_lab(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response:
    """
    Get the user groups for a virtual lab.

    Args:
        virtual_lab_id: ID of the virtual lab

    Returns:
        Response: List of user groups for the virtual lab
    """
    return await usecases.get_user_virtual_lab_groups(
        session=session, virtual_lab_id=virtual_lab_id, auth=auth
    )
