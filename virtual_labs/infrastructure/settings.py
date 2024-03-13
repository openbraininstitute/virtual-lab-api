from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import PostgresDsn, ValidationInfo, field_validator
from pydantic_core import MultiHostUrl, Url
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    APP_NAME: str = "virtual-lab-manager service"
    DEBUG_DATABASE_ECHO: bool = False
    CORS_ORIGINS: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 15432
    POSTGRES_USER: str = "vlm"
    POSTGRES_PASSWORD: str = "vlm"
    POSTGRES_DB: str = "vlm"
    DATABASE_URI: PostgresDsn = MultiHostUrl("postgresql://vlm:vlm@localhost:15432/vlm")
    NEXUS_DELTA_URI: Url = Url("https://dev.nise.bbp.epfl.ch/nexus/v1")

    KC_SERVER_URI: str = "http://localhost:9090/"
    KC_USER_NAME: str = "admin"
    KC_PASSWORD: str = "admin"
    KC_CLIENT_ID: str = "obpapp"
    KC_CLIENT_SECRET: str = "obp-secret"
    KC_REALM_NAME: str = "obp-realm"

    @field_validator("DATABASE_URI", mode="before")
    @classmethod
    def build_db_connection(cls, v: Optional[str], values: ValidationInfo) -> Any:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql",
            username=values.data.get("POSTGRES_USER"),
            password=values.data.get("POSTGRES_PASSWORD"),
            host=values.data.get("POSTGRES_HOST"),
            port=values.data.get("POSTGRES_PORT"),
            path=f"{values.data.get('POSTGRES_DB') or ''}",
        )


settings = Settings()
