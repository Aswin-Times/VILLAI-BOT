"""Application settings, read from the environment or `.env`."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://vilai:vilai@localhost:5432/vilai"
    datagov_api_key: SecretStr | None = None
    ceda_api_key: SecretStr | None = None
