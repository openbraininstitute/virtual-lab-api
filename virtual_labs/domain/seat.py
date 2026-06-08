from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, Field


class ProvisionSeatsBody(BaseModel):
    """Payload for provisioning seats for a virtual lab."""

    virtual_lab_id: UUID4
    number_of_seats: int = Field(..., gt=0)


class SeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    virtual_lab_id: UUID4 | None
    institution_id: UUID4
    batch_id: UUID4
    is_consumed: bool
    active_project_id: UUID4 | None
    expiry_date: datetime


class ProvisionSeatsResponse(BaseModel):
    seats: list[SeatOut]
    total_credits_topped_up: float
