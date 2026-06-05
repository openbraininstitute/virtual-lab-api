from typing import Annotated, Dict, List

from fastapi import APIRouter, Body, Depends, Query, Response
from pydantic import UUID4, BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import (
    verify_service_admin,
    verify_vlab_read,
    verify_vlab_write,
    verity_member_invite,
)
from virtual_labs.core.ledger.modules.virtual_lab import REGULAR_LAB_POLICY
from virtual_labs.core.types import UserGroup, UserRoleEnum, VliAppResponse
from virtual_labs.domain.common import ListResponse, PaginationRequest
from virtual_labs.domain.invite import InvitePayload
from virtual_labs.domain.labs import (
    InvitationResponse,
    LabResponse,
    SearchLabResponse,
    VirtualLabComputeCellUpdate,
    VirtualLabCreate,
    VirtualLabDetailExpand,
    VirtualLabDetails,
    VirtualLabOut,
    VirtualLabStats,
    VirtualLabUpdate,
    VirtualLabUser,
    VirtualLabUsers,
    VirtualLabWithAdmins,
    VirtualLabWithInviteDetails,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import a_verify_jwt, verify_jwt
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.usecases import labs as usecases
from virtual_labs.usecases.labs.check_virtual_lab_name_exists import LabExists
from virtual_labs.usecases.labs.list_virtual_labs import ListVirtualLabsQuery

router = APIRouter(prefix="/virtual-labs", tags=["Virtual Labs Endpoints"])


@router.get(
    "",
    response_model=ListResponse[VirtualLabDetails],
    summary="List the virtual labs the requester is a member of",
)
async def list_virtual_labs(
    params: Annotated[ListVirtualLabsQuery, Query()],
    db: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> ListResponse[VirtualLabDetails]:
    return await usecases.list_virtual_labs_use_case(
        session=db,
        auth=auth,
        scope=params.scope,
        admin_access_only=params.admin_access_only,
        order_by=params.order_by,
        order_direction=params.order_direction,
        query=params.query,
        pagination=params,
    )


@router.get(
    "/self",
    response_model=LabResponse[VirtualLabDetails | None],
    summary="Get the requester's owned virtual lab",
)
async def get_my_virtual_lab(
    db: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> LabResponse[VirtualLabDetails | None]:
    return LabResponse[VirtualLabDetails | None](
        message="Your virtual lab",
        data=await usecases.get_my_virtual_lab_use_case(session=db, auth=auth),
    )


@router.get(
    "/requests",
    response_model=ListResponse[VirtualLabWithInviteDetails],
    summary="List pending virtual-lab invitations for the requester",
)
async def list_pending_virtual_labs(
    pagination: Annotated[PaginationRequest, Query()],
    db: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> ListResponse[VirtualLabWithInviteDetails]:
    return await usecases.list_pending_virtual_labs_use_case(
        session=db,
        auth=auth,
        pagination=pagination,
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
    response_model=VirtualLabWithAdmins,
    response_model_exclude_none=False,
    summary="Get non deleted virtual lab by id",
)
@verify_vlab_read
async def get_virtual_lab(
    virtual_lab_id: UUID4,
    expand: Annotated[list[VirtualLabDetailExpand] | None, Query()] = None,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VirtualLabWithAdmins:
    return await usecases.get_virtual_lab(
        session,
        virtual_lab_id,
        expand=expand,
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


@router.post("", response_model=VirtualLabDetails)
async def create_virtual_lab(
    lab: VirtualLabCreate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> VirtualLabDetails:
    return await usecases.create_virtual_lab(
        session, lab, auth, policy=REGULAR_LAB_POLICY
    )


@router.patch("/{virtual_lab_id}", response_model=LabResponse[VirtualLabOut])
@verify_vlab_write
async def update_virtual_lab(
    virtual_lab_id: UUID4,
    lab: VirtualLabUpdate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> LabResponse[VirtualLabOut]:
    updated_lab = await usecases.update_virtual_lab(
        session, virtual_lab_id, lab=lab, user_id=get_user_id_from_auth(auth)
    )
    return LabResponse[VirtualLabOut](message="Updated virtual lab", data=updated_lab)


@router.patch(
    "/{virtual_lab_id}/compute-cell",
    response_model=LabResponse[VirtualLabOut],
    summary="Update virtual lab compute cell (Service Admin only)",
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def update_virtual_lab_compute_cell(
    virtual_lab_id: UUID4,
    payload: VirtualLabComputeCellUpdate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[VirtualLabOut]:
    from virtual_labs.usecases.labs.update_virtual_lab_compute_cell import (
        update_virtual_lab_compute_cell as update_compute_cell_usecase,
    )

    updated_lab = await update_compute_cell_usecase(
        session, virtual_lab_id, compute_cell=payload.compute_cell
    )
    return LabResponse[VirtualLabOut](
        message="Updated virtual lab compute cell", data=updated_lab
    )


@router.post(
    "/{virtual_lab_id}/invites",
    summary="Invite user to lab by email",
    response_model=LabResponse[InvitationResponse],
)
@verity_member_invite
async def invite_user_to_virtual_lab(
    virtual_lab_id: UUID4,
    invite_details: InvitePayload,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[InvitationResponse]:
    invite_id = await usecases.invite_user_to_lab(
        virtual_lab_id,
        inviter_id=get_user_id_from_auth(auth),
        invite_details=invite_details,
        db=session,
    )
    return LabResponse[InvitationResponse](
        message="Invite sent to user", data=InvitationResponse(id=invite_id)
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
    invite_details: InvitePayload,
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


class EmailCheckRequest(BaseModel):
    emails: list[EmailStr]


@router.post("/{virtual_lab_id}/missing-student-emails", response_model=list[str])
@verify_vlab_write
async def check_unassigned_emails(
    virtual_lab_id: UUID4,
    payload: EmailCheckRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> list[EmailStr]:
    return await usecases.get_missing_contact_emails(
        session, virtual_lab_id, payload.emails
    )
