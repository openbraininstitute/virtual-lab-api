from datetime import datetime
from typing import Optional

from pydantic import UUID4, BaseModel, ConfigDict, Field

# ──────────────────────────────────────────────────────────────────────
# Request schemas
# ──────────────────────────────────────────────────────────────────────


class ProvisionSeatsBody(BaseModel):
    """Payload for provisioning seats for a course."""

    course_id: UUID4
    number_of_seats: int = Field(..., gt=0, le=100)


# ──────────────────────────────────────────────────────────────────────
# Response schemas
# ──────────────────────────────────────────────────────────────────────


class EnrolmentSummary(BaseModel):
    """Enrolment info nested in seat responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    course_id: UUID4
    project_id: UUID4 | None = None
    contact_email: str
    student_id: str
    claimed_by: UUID4 | None = None
    is_dropped: bool


class SeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    course_id: UUID4
    institution_id: UUID4
    batch_id: UUID4
    is_consumed: bool
    enrolment_id: UUID4 | None = None
    credit_value: int
    expiry_date: datetime
    created_at: datetime


class SeatDetailOut(SeatOut):
    """Seat with nested enrolment summary."""

    enrolment: EnrolmentSummary | None = None


class ProvisionSeatsResponse(BaseModel):
    seats: list[SeatOut]
    total_credits_topped_up: float


class ListSeatsResponse(BaseModel):
    seats: list[SeatDetailOut]


# ──────────────────────────────────────────────────────────────────────
# Batch search response schemas
# ──────────────────────────────────────────────────────────────────────


class InstitutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    name: str
    contact_email: str


class CourseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    virtual_lab_id: UUID4
    virtual_lab_name: str
    institution_id: UUID4
    template_project_id: UUID4
    status: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class SeatBatchOut(BaseModel):
    """A single batch of seats."""

    batch_id: UUID4
    created_at: datetime
    expiry_date: datetime
    number_of_seats: int
    seats: list[SeatOut]


class SeatBatchSearchResponse(BaseModel):
    """Response for searching seat batches."""

    institution: InstitutionSummary
    course: CourseSummary
    batches: list[SeatBatchOut]
