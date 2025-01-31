from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class NotebookCreate(BaseModel):
    project_id: UUID
    github_file_url: str


class NotebookRead(BaseModel):
    id: UUID
    project_id: UUID
    github_file_url: str
    created_at: datetime
    updated_at: datetime
