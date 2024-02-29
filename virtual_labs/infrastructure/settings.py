from typing import Any, Dict, Optional, Union

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, PostgresDsn, validator
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
    DATABASE_URI: Union[
        PostgresDsn, AnyHttpUrl
    ] = "postgresql://vlm:vlm@localhost:15432/vlm"

    @validator("DATABASE_URI", pre=True)
    def build_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql",
            username=values.get("POSTGRES_USER"),
            password=values.get("POSTGRES_PASSWORD"),
            host=values.get("POSTGRES_HOST"),
            port=values.get("POSTGRES_PORT"),
            path=f"{values.get('POSTGRES_DB') or ''}",
        )


settings = Settings()
