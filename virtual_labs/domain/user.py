from pydantic import UUID4, BaseModel


class ShortenedUser(BaseModel):
    id: UUID4
    username: str

    class Config:
        from_attributes = True
