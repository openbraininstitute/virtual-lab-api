from typing import Optional, TypeVar, Generic
from pydantic import BaseModel, UUID4, field_validator, JsonValue
from datetime import datetime


T = TypeVar("T")


class LabResponse(BaseModel, Generic[T]):
    message: str
    data: T


class VirtualLabBase(BaseModel):
    name: str
    description: str
    reference_email: str
    budget: float

    @field_validator("budget")
    @classmethod
    def check_budget_greater_than_0(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Budget should be greater than 0")

        return v


class VirtualLabCreate(VirtualLabBase):
    plan_id: int


class VirtualLabUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    reference_email: str | None = None
    budget: float | None = None
    plan_id: int | None = None

    @field_validator("budget")
    @classmethod
    def check_budget_greater_than_0(cls, v: float | None) -> float | None:
        if v is None:
            return v

        if v <= 0:
            raise ValueError("Budget should be greater than 0")
        return v


class PlanDomain(BaseModel):
    id: int
    name: str
    price: float
    features: JsonValue

    class Config:
        from_attributes = True


class ProjectStar(BaseModel):
    id: UUID4

    class Config:
        from_attributes = True


class VirtualLabProject(BaseModel):
    id: UUID4
    name: str
    description: str | None
    project_stars: list[ProjectStar] | None = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VirtualLabDomain(VirtualLabBase):
    id: UUID4
    nexus_organization_id: str

    deleted: bool
    plan: PlanDomain

    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    projects: list[VirtualLabProject] | None = None

    class Config:
        from_attributes = True


class Labs(BaseModel):
    virtual_labs: list[VirtualLabDomain]


class Lab(BaseModel):
    virtual_lab: VirtualLabDomain


class AllPlans(BaseModel):
    all_plans: list[PlanDomain]
