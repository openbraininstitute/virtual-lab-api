from typing import Any, List

from pydantic import BaseModel


class UserRepresentation(BaseModel):
    id: str
    username: str
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
    subGroups: List[Any]

    class Config:
        from_attributes = True
