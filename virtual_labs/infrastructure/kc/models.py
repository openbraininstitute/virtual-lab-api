from typing import Annotated, Any, List, Optional, TypedDict

from pydantic import BaseModel, EmailStr, Field


class BaseUserRepresentation(BaseModel):
    username: str
    firstName: str | None = None
    lastName: str | None = None
    email: EmailStr | None
    emailVerified: bool
    createdTimestamp: int
    enabled: bool
    totp: bool
    disableableCredentialTypes: List[Any]
    requiredActions: List[Any]
    notBefore: int

    class Config:
        from_attributes = True


class UserRepresentation(BaseUserRepresentation):
    id: str


class UserNotInKCRepresentation(BaseUserRepresentation):
    id: None


class GroupRepresentation(BaseModel):
    id: str
    name: str
    path: str

    class Config:
        from_attributes = True


class AuthUser(BaseModel):
    sid: str
    sub: str
    username: Annotated[str, Field(alias="preferred_username")]
    email: EmailStr
    email_verified: bool
    name: Optional[str] = None

    class Config:
        populate_by_name = True


class ClientToken(BaseModel):
    access_token: str
    expires_in: int

    class Config:
        from_attributes = True


CreatedGroup = TypedDict("CreatedGroup", {"id": str, "name": str})


class Address(TypedDict):
    street_address: str
    postal_code: str
    locality: str
    region: str
    country: str


class UserInfo(TypedDict):
    preferred_username: str
    email: str
    given_name: str
    family_name: str
    email_verified: bool
    address: Address
