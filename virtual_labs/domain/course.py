from datetime import datetime
from typing import Optional

from pydantic import UUID4, BaseModel, ConfigDict, Field, model_validator


class CourseCreateBody(BaseModel):
    """Payload for creating a course by assigning an existing virtual lab and project."""

    virtual_lab_id: UUID4
    template_project_id: UUID4
    institution_id: UUID4
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    last_drop_date: Optional[datetime] = None


class CourseUpdateBody(BaseModel):
    """Payload for updating a draft course."""

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    last_drop_date: Optional[datetime] = None
    institution_id: Optional[UUID4] = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    virtual_lab_id: UUID4
    institution_id: UUID4
    template_project_id: UUID4
    status: str
    credits_per_seat: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    last_drop_date: Optional[datetime] = None


class CourseDetailOut(BaseModel):
    """Course with resolved virtual lab and institution names."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    virtual_lab_id: UUID4
    virtual_lab_name: str
    institution_id: UUID4
    institution_name: str
    template_project_id: UUID4
    status: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    last_drop_date: Optional[datetime] = None


# ──────────────────────────────────────────────────────────────────────
# Seat assignment schemas
# ──────────────────────────────────────────────────────────────────────


class SeatAssignmentEntry(BaseModel):
    """A single student to assign a seat to."""

    student_id: str
    email: str


class AssignSeatsBody(BaseModel):
    """Payload for assigning seats to users."""

    students: list[SeatAssignmentEntry] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _unique_ids_and_emails(self) -> "AssignSeatsBody":
        ids = [s.student_id for s in self.students]
        emails = [s.email for s in self.students]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate student_id in request")
        if len(emails) != len(set(emails)):
            raise ValueError("Duplicate email in request")
        return self


class SeatAssignmentResult(BaseModel):
    """Result for a single seat assignment attempt."""

    student_id: str
    email: str
    assignment_successful: bool = True
    seat_id: UUID4
    enrolment_id: UUID4 | None = None
    project_id: UUID4 | None = None
    credit_transferred_amount: float = 0
    email_sent: bool = True
    error: str | None = None


class AssignSeatResponse(BaseModel):
    results: list[SeatAssignmentResult]


# ──────────────────────────────────────────────────────────────────────
# Seat drop schemas
# ──────────────────────────────────────────────────────────────────────


class DropSeatsBody(BaseModel):
    """Payload for dropping (releasing) seats."""

    seat_ids: list[UUID4] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "DropSeatsBody":
        if len(self.seat_ids) != len(set(self.seat_ids)):
            raise ValueError("Duplicate seat_id in request")
        return self


class SeatDropResult(BaseModel):
    """Result for a single seat drop attempt."""

    seat_id: UUID4
    drop_successful: bool
    error: str | None = None


class DropSeatResponse(BaseModel):
    results: list[SeatDropResult]
