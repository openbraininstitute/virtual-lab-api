from datetime import datetime
from typing import Annotated, Any

from pydantic import UUID4, BaseModel, Field, field_validator


class ShortenedUser(BaseModel):
    id: UUID4
    username: str
    createdTimestamp: Annotated[datetime, Field(alias="created_at", default="")]

    @field_validator("createdTimestamp", mode="before")
    @classmethod
    def convert_timestamp(cls, v: str) -> Any:
        if isinstance(v, int):
            return datetime.fromtimestamp(v / 1000)
        return v

    class Config:
        from_attributes = True
        populate_by_name = True
