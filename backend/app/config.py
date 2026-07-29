from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Sirius Gate API"
    environment: str = "development"
    database_url: str = "sqlite:///./sirius_gate.db"
    organizer_code: str = "ORBIT-ADMIN"
    security_secret: str = "development-token-secret-change-me"
    code_hmac_secret: str = "development-code-secret-change-me"
    access_token_ttl_minutes: int = Field(default=720, ge=5, le=10_080)
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173,"
        "http://localhost:4174,http://127.0.0.1:4174"
    )

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
