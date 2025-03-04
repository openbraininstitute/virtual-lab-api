from datetime import datetime
from typing import Generic, TypeVar

from pydantic import (
    UUID4,
    BaseModel,
    EmailStr,
    Field,
    JsonValue,
)

from virtual_labs.domain.user import UserWithInviteStatus

T = TypeVar("T")


class LabResponse(BaseModel, Generic[T]):
    message: str
    data: T


class VirtualLabBase(BaseModel):
    name: str = Field(max_length=250)
    description: str
    reference_email: EmailStr
    entity: str


class VirtualLabUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    reference_email: EmailStr | None = None
    plan_id: int | None = None
    entity: str | None = None


class PlanDomain(BaseModel):
    id: int
    name: str
    price: float
    features: JsonValue

    class Config:
        from_attributes = True


class VirtualLabDetails(VirtualLabBase):
    id: UUID4
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class VirtualLabWithInviteDetails(VirtualLabDetails):
    invite_id: UUID4

    class Config:
        from_attributes = True


class VirtualLabUsers(BaseModel):
    users: list[UserWithInviteStatus]


class VirtualLabUser(BaseModel):
    user: UserWithInviteStatus


class VirtualLabOut(BaseModel):
    virtual_lab: VirtualLabDetails


class VirtualLabCreate(VirtualLabBase):
    pass


class CreateLabOut(BaseModel):
    virtual_lab: VirtualLabDetails


class SearchLabResponse(BaseModel):
    virtual_labs: list[VirtualLabDetails]


class AllPlans(BaseModel):
    all_plans: list[PlanDomain]


class InviteSent(BaseModel):
    invite_id: UUID4
