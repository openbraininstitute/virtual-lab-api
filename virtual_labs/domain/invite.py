from typing import Literal

from pydantic import UUID4, BaseModel, EmailStr

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.email.email_utils import InviteOrigin


class AddUser(BaseModel):
    email: EmailStr
    role: UserRoleEnum


class InviteOut(BaseModel):
    invite_id: UUID4
    virtual_lab_id: UUID4
    project_id: UUID4 | None
    origin: InviteOrigin
    accepted: Literal["accepted", "already_accepted"] | None
