"""Application settings, read from the environment or `.env`."""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://vilai:vilai@localhost:5432/vilai"
    datagov_api_key: SecretStr | None = None
    ceda_api_key: SecretStr | None = None

    # Keys the pre-consent conversation hash. Changing it forgets in-progress onboardings.
    phone_hash_secret: SecretStr | None = None

    twilio_account_sid: str | None = None
    twilio_auth_token: SecretStr | None = None
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    public_base_url: str | None = None  # the URL Twilio calls, used to verify signatures

    intent_provider: Literal["anthropic", "rules"] = "rules"
    anthropic_api_key: SecretStr | None = None
