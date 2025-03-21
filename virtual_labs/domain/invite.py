from typing import Literal

from pydantic import UUID4, BaseModel, EmailStr

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.email.email_utils import InviteOrigin


class AddUser(BaseModel):
    email: EmailStr
    role: UserRoleEnum


class DeleteLabInviteRequest(AddUser):
    """Request body for deleting a lab invite"""

    pass


class InviteDetailsOut(BaseModel):
    accepted: bool
    invite_id: UUID4
    inviter_full_name: str
    origin: InviteOrigin
    project_id: UUID4 | None
    project_name: str | None
    virtual_lab_id: UUID4
    virtual_lab_name: str | None


class InviteOut(BaseModel):
    invite_id: UUID4
    virtual_lab_id: UUID4
    project_id: UUID4 | None
    origin: InviteOrigin
    accepted: Literal["accepted", "already_accepted"] | None
