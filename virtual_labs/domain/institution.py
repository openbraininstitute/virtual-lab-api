from typing import Optional

from pydantic import UUID4, BaseModel, ConfigDict, EmailStr, Field, field_validator


class InstitutionCreate(BaseModel):
    name: str = Field(max_length=250)
    contact_email: EmailStr

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class InstitutionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=250)
    contact_email: Optional[EmailStr] = None


class InstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    name: str
    contact_email: str
