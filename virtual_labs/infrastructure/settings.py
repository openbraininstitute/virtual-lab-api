from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "virtual-lab-manager service"
    DATABASE_URI: str = Field(
        alias="DATABASE_URL", default="postgresql://vlm:vlm@localhost:15432/vlm"
    )
    DEBUG_DATABASE_ECHO: bool = False
    CORS_ORIGINS: str = ""


settings = Settings()
