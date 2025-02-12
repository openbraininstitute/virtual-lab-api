from typing import Annotated

import dns.resolver
from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

CODE_LENGTH = 6
MAX_ATTEMPTS = 3
LOCK_TIME_MINUTES = 15


EmailVerificationCode = Annotated[
    str, StringConstraints(min_length=6, max_length=6, pattern=r"^\d{6}$")
]


class Email(BaseModel):
    email: EmailStr

    @field_validator("email")
    def validate_email(cls, value: str) -> str:
        # DNS validation (check MX records)
        domain = value.split("@")[-1]
        try:
            # Check if the domain has MX records
            dns.resolver.resolve(domain, "MX")
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            raise ValueError(
                "Email domain does not exist or is not configured to receive emails"
            )

        return value


class InitiateEmailVerificationPayload(Email):
    virtual_lab_name: str


class EmailVerificationPayload(Email):
    virtual_lab_name: str
    code: EmailVerificationCode


class VerificationCodeEmailDetails(BaseModel):
    recipient: EmailStr
    code: EmailVerificationCode
