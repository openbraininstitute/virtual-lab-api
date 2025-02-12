from typing import Annotated

import dns.resolver
from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

VerificationCode = Annotated[
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


class EmailVerificationPayload(Email):
    code: VerificationCode
