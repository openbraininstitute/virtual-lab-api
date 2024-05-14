from datetime import datetime
from typing import Generic, TypeVar

from pydantic import (
    UUID4,
    BaseModel,
    EmailStr,
    Field,
    JsonValue,
    computed_field,
)

from virtual_labs.domain.invite import AddUser
from virtual_labs.domain.user import UserWithInviteStatus
from virtual_labs.shared.utils.billing import amount_to_float

T = TypeVar("T")


class LabResponse(BaseModel, Generic[T]):
    message: str
    data: T


class VirtualLabBase(BaseModel):
    name: str = Field(max_length=250)
    description: str
    reference_email: EmailStr
    entity: str
    budget_amount: int = Field(exclude=True, default=0)

    @computed_field
    def budget(self) -> float:
        return amount_to_float(self.budget_amount)


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
    plan_id: int
    created_at: datetime
    nexus_organization_id: str

    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class VirtualLabUsers(BaseModel):
    users: list[UserWithInviteStatus]


class VirtualLabUser(BaseModel):
    user: UserWithInviteStatus


class VirtualLabOut(BaseModel):
    virtual_lab: VirtualLabDetails


class VirtualLabCreate(VirtualLabBase):
    plan_id: int
    include_members: list[AddUser] | None = None


class CreateLabOut(BaseModel):
    virtual_lab: VirtualLabDetails
    successful_invites: list[AddUser]
    failed_invites: list[AddUser]


class SearchLabResponse(BaseModel):
    virtual_labs: list[VirtualLabDetails]


class AllPlans(BaseModel):
    all_plans: list[PlanDomain]


class InviteSent(BaseModel):
    invite_id: UUID4
