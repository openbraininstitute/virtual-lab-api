from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "virtual-lab service"
    API_V1_STR: str = "/api/v1"
    DATABASE_URI: str = Field(
        alias="DATABASE_URL", default="postgresql://vlm:vlm@localhost:15432/vlm"
    )
    DEBUG_DATABASE_ECHO: bool = False
    CORS_ORIGINS: str = ""


settings = Settings()
print(settings.model_dump())
