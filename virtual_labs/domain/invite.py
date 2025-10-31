from typing import Literal

from pydantic import UUID4, BaseModel, EmailStr

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.email.email_utils import InviteOrigin


class InvitePayload(BaseModel):
    email: EmailStr
    role: UserRoleEnum


class InvitationResponse(BaseModel):
    accepted: bool
    invite_id: UUID4
    inviter_full_name: str
    origin: InviteOrigin
    virtual_lab_id: UUID4
    virtual_lab_name: str | None
    project_id: UUID4 | None
    project_name: str | None


class InviteOut(BaseModel):
    invite_id: UUID4
    virtual_lab_id: UUID4
    origin: InviteOrigin
    accepted: Literal["accepted", "already_accepted"] | None
