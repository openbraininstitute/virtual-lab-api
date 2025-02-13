from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import UUID4, BaseModel, HttpUrl

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


class BudgetTopUpRequest(BaseModel):
    amount: float


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


class JobSubtype(Enum):
    ML_LLM = "ml-llm"
    ML_RAG = "ml-rag"
    ML_RETRIEVAL = "ml-retrieval"
    STORAGE = "storage"
    SINGLE_CELL_SIM = "single-cell-sim"


# TODO: Update according to the STORAGE report type
class ProjectJobReport(BaseModel):
    job_id: UUID4
    user_id: UUID4
    type: JobType
    subtype: JobSubtype
    reserved_at: datetime | None = None
    started_at: datetime | None = None
    amount: str
    count: int
    reserved_amount: str
    reserved_count: int


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
