from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints

CODE_LENGTH = 6
MAX_ATTEMPTS = 3
LOCK_TIME_MINUTES = 15


EmailVerificationCode = Annotated[
    str, StringConstraints(min_length=6, max_length=6, pattern=r"^\d{6}$")
]


class Email(BaseModel):
    email: EmailStr

    # @field_validator("email")
    # def validate_email(cls, value: str) -> str:
    #     # DNS validation (check MX records)
    #     domain = value.split("@")[-1]
    #     try:
    #         # Check if the domain has MX records
    #         dns.resolver.resolve(domain, "MX")
    #     except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
    #         raise ValueError(
    #             "Email domain does not exist or is not configured to receive emails"
    #         )

    #     return value


class InitiateEmailVerificationPayload(Email):
    virtual_lab_name: str

    @property
    def name(self) -> str:
        return self.virtual_lab_name.strip()


class EmailVerificationPayload(Email):
    virtual_lab_name: str
    code: EmailVerificationCode

    @property
    def name(self) -> str:
        return self.virtual_lab_name.strip()


class VerificationCodeEmailDetails(BaseModel):
    recipient: EmailStr
    code: EmailVerificationCode
    virtual_lab_name: str
    expire_at: str


class VerificationCodeEmailResponseData(BaseModel):
    verified_at: datetime | None = None
    is_verified: bool
    remaining_attempts: int
    remaining_time: int
    locked: bool
    code_sent: bool | None = None


class VerificationCodeEmailResponse(BaseModel):
    message: str
    data: VerificationCodeEmailResponseData
