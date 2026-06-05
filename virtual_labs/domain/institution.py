from typing import Optional

from pydantic import UUID4, BaseModel, ConfigDict, EmailStr, Field


class InstitutionCreate(BaseModel):
    name: str = Field(max_length=250)
    contact_email: EmailStr


class InstitutionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=250)
    contact_email: Optional[EmailStr] = None


class InstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    name: str
    contact_email: str
