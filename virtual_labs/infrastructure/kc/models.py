from typing import Annotated, Any, List

from pydantic import UUID4, BaseModel, EmailStr, Field


class UserRepresentation(BaseModel):
    id: str
    username: str
    firstName: str | None = None
    lastName: str | None = None
    emailVerified: bool
    createdTimestamp: int
    enabled: bool
    totp: bool
    disableableCredentialTypes: List[Any]
    requiredActions: List[Any]
    notBefore: int

    class Config:
        from_attributes = True


class GroupRepresentation(BaseModel):
    id: str
    name: str
    path: str

    class Config:
        from_attributes = True


class AuthUser(BaseModel):
    sid: UUID4
    sub: str  # nexus format: f:uuid4:username
    username: Annotated[str, Field(alias="preferred_username")]
    email: EmailStr
    email_verified: bool
    name: str
