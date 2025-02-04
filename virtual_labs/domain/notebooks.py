from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, UrlConstraints, field_validator
from pydantic_core import Url

HttpsUrl = Annotated[Url, UrlConstraints(max_length=2083, allowed_schemes=["https"])]


class UrlValidator(BaseModel):
    url: HttpsUrl


class NotebookCreate(BaseModel):
    github_file_url: str

    @field_validator("github_file_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        UrlValidator.model_validate({"url": value})
        return value


class Notebook(BaseModel):
    id: UUID
    project_id: UUID
    github_file_url: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
