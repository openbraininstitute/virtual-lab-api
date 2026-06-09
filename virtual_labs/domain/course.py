from datetime import datetime
from typing import Optional

from pydantic import UUID4, BaseModel, ConfigDict, Field, model_validator

from virtual_labs.domain.seat import SeatOut


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


class AssignSeatResponse(BaseModel):
    seats: list[SeatOut]
