from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import UUID4, BaseModel, EmailStr, StringConstraints

CODE_LENGTH = 6


EmailVerificationCode = Annotated[
    str, StringConstraints(min_length=6, max_length=6, pattern=r"^\d{6}$")
]


class VerificationCodeStatus(Enum):
    LOCKED = "locked"
    NOT_MATCH = "not_match"
    REGISTERED = "registered"
    CODE_SENT = "code_sent"
    EXPIRED = "expired"
    VERIFIED = "verified"
    WAITING = "waiting"


class Email(BaseModel):
    email: EmailStr


class VirtualLabContext(BaseModel):
    virtual_lab_id: UUID4


class InitiateEmailVerificationPayload(
    Email,
):
    pass


class EmailVerificationPayload(Email):
    code: EmailVerificationCode


class VerificationCodeEmailDetails(BaseModel):
    recipient: EmailStr
    code: EmailVerificationCode
    virtual_lab_id: UUID
    virtual_lab_name: str
    expire_at: str


class VerificationCodeEmailResponseData(BaseModel):
    message: str
    status: VerificationCodeStatus
    remaining_time: int | None
    remaining_attempts: int | None


class VerificationCodeEmailResponse(BaseModel):
    message: str
    data: VerificationCodeEmailResponseData
