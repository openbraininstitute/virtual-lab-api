from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Generic, Self, TypeVar
from uuid import UUID

from pydantic import (
    UUID4,
    AwareDatetime,
    BaseModel,
    HttpUrl,
    field_validator,
    model_validator,
    ValidationInfo,
)

T = TypeVar("T")


class VlabAccount(BaseModel):
    id: UUID4
    name: str


class ProjAccount(BaseModel):
    id: UUID4
    name: str


class BaseAccountingResponse(BaseModel):
    message: str


class VlabAccountCreationResponse(BaseAccountingResponse):
    data: VlabAccount


class ProjAccountCreationResponse(BaseAccountingResponse):
    data: ProjAccount


class ProjBalance(BaseModel):
    proj_id: UUID4
    balance: str
    reservation: str


class VlabBalance(BaseModel):
    vlab_id: UUID4
    balance: str
    projects: list[ProjBalance] | None = None


class ProjBalanceResponse(BaseAccountingResponse):
    data: ProjBalance


class VlabBalanceResponse(BaseAccountingResponse):
    data: VlabBalance


class BudgetTopUpResponse(BaseAccountingResponse):
    data: None


class BudgetAssignRequest(BaseModel):
    amount: float


class BudgetAssignResponse(BaseAccountingResponse):
    data: None


class BudgetReverseRequest(BaseModel):
    amount: float


class BudgetReverseResponse(BaseAccountingResponse):
    data: None


class BudgetMoveResponse(BaseAccountingResponse):
    data: None


class JobType(Enum):
    ONESHOT = "oneshot"
    LONGRUN = "longrun"
    STORAGE = "storage"


# TODO: Get these types from the accounting SDK module
class JobSubtype(Enum):
    ML_LLM = "ml-llm"
    ML_RAG = "ml-rag"
    ML_RETRIEVAL = "ml-retrieval"
    NOTEBOOK = "notebook"
    SINGLE_CELL_BUILD = "single-cell-build"
    SINGLE_CELL_SIM = "single-cell-sim"
    SMALL_CIRCUIT_SIM = "small-circuit-sim"
    STORAGE = "storage"
    SYNAPTOME_BUILD = "synaptome-build"
    SYNAPTOME_SIM = "synaptome-sim"


# TODO: Update according to the STORAGE report type
class ProjectJobReport(BaseModel):
    job_id: UUID4
    user_id: UUID4
    name: str | None = None
    type: JobType
    subtype: JobSubtype
    reserved_at: datetime | None = None
    started_at: datetime | None = None
    amount: str
    count: int | None = None
    reserved_amount: str
    reserved_count: int | None = None
    duration: int | None = None
    reserved_duration: int | None = None

    @field_validator("count", "reserved_count", mode="after")
    def validate_oneshot_required_fields(
        cls, v: int | None, info: ValidationInfo
    ) -> int | None:
        job_type = info.data.get("type")
        if job_type == JobType.ONESHOT and v is None:
            raise ValueError(f"{info.field_name} is required for oneshot jobs.")
        return v

    @field_validator("duration", "reserved_duration", mode="after")
    def validate_longrun_required_fields(
        cls, v: int | None, info: ValidationInfo
    ) -> int | None:
        job_type = info.data.get("type")
        if job_type == JobType.LONGRUN and v is None:
            raise ValueError(f"{info.field_name} is required for longrun jobs.")
        return v


class VirtualLabJobReport(ProjectJobReport):
    proj_id: UUID4


class PaginatedMeta(BaseModel):
    page: int
    page_size: int
    total_pages: int
    total_items: int


class PaginatedLinks(BaseModel):
    self: HttpUrl
    prev: HttpUrl | None
    next: HttpUrl | None
    first: HttpUrl
    last: HttpUrl


class ReportsResponseData(BaseModel, Generic[T]):
    items: list[T]
    meta: PaginatedMeta
    links: PaginatedLinks


class VirtualLabReportsResponse(BaseAccountingResponse):
    data: ReportsResponseData[VirtualLabJobReport]


class ProjectReportsResponse(BaseAccountingResponse):
    data: ReportsResponseData[ProjectJobReport]


class VirtualLabTopUpResponse(BaseAccountingResponse):
    data: None


class CreateDiscountRequest(BaseModel):
    vlab_id: UUID
    discount: Decimal
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None

    @field_validator("discount")
    def validate_discount(cls, v: Decimal) -> Decimal:
        if v < Decimal(0) or v > Decimal(1):
            raise ValueError("Discount must be between 0 and 1")
        return v

    @model_validator(mode="after")
    def check_validity_interval(self) -> Self:
        """Check that valid_to is greater than valid_from, if provided."""
        if self.valid_to is not None and self.valid_from >= self.valid_to:
            err = "valid_to must be greater than valid_from"
            raise ValueError(err)
        return self


class Discount(CreateDiscountRequest):
    id: int


class CreateDiscountResponse(BaseAccountingResponse):
    data: Discount
