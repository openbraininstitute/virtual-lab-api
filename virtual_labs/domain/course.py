from datetime import date
from typing import Optional

from pydantic import UUID4, BaseModel, ConfigDict


class CourseCreateBody(BaseModel):
    """Payload for creating a course by assigning an existing virtual lab and project."""

    virtual_lab_id: UUID4
    template_project_id: UUID4
    institution_id: UUID4
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    last_drop_date: Optional[date] = None


class CourseUpdateBody(BaseModel):
    """Payload for updating a draft course."""

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    last_drop_date: Optional[date] = None
    institution_id: Optional[UUID4] = None


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
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    last_drop_date: Optional[date] = None
