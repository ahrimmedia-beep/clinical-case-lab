"""Runtime settings, read from environment variables (12-factor)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "test", "prod"] = "local"

    # Local / CI: a full URL. Cloud Run: CLOUD_SQL_INSTANCE + DB_* parts (unix socket).
    database_url: str = "postgresql+asyncpg://caselab:caselab@localhost:5434/caselab"
    cloud_sql_instance: str | None = None  # "project:region:instance"
    db_user: str = "caselab"
    db_password: SecretStr | None = None
    db_name: str = "caselab"

    cors_origins: list[str] = ["http://localhost:3000"]
    internal_api_key: SecretStr | None = None
    max_case_bytes: int = 262_144

    gcp_project: str | None = None
    gemini_location: str = "global"
    claude_region: str = "global"
    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    extract_rate_per_minute: int = 5
    extract_daily_cap: int = 200

    @property
    def sqlalchemy_url(self) -> str:
        if self.cloud_sql_instance:
            password = self.db_password.get_secret_value() if self.db_password else ""
            return (
                f"postgresql+asyncpg://{quote(self.db_user)}:{quote(password)}@/{self.db_name}"
                f"?host=/cloudsql/{self.cloud_sql_instance}"
            )
        return self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
