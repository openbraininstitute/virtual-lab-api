from datetime import date
from typing import Optional

from pydantic import UUID4, BaseModel, ConfigDict, EmailStr, Field

from virtual_labs.domain.labs import ComputeCell


class CourseCreateBody(BaseModel):
    # Fields for creating the underlying virtual lab
    name: str = Field(max_length=250)
    description: str
    reference_email: EmailStr | None = None
    entity: str
    compute_cell: ComputeCell = ComputeCell.CELL_A

    # Course-specific fields
    institution_id: UUID4
    template_project_id: UUID4
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    last_drop_date: Optional[date] = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    virtual_lab_id: UUID4
    institution_id: UUID4
    template_project_id: UUID4
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    last_drop_date: Optional[date] = None
