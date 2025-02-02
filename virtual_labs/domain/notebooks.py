from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, HttpUrl, field_validator


class UrlValidator(BaseModel):
    url: HttpUrl


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
