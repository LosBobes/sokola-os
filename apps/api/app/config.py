"""Application settings, loaded from environment (prefix ``SOKOLA_``).

Secrets never live in the repo. Local dev reads ``.env``; production injects
real environment variables. The dev-only auth adapter is gated here and refuses
to run outside a local/test environment (see :mod:`app.security`).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOKOLA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = "local"
    database_url: str = "postgresql+psycopg://sokola:sokola@localhost:55432/sokola"

    # Dev-only header auth. Enforced off outside local/test at startup.
    allow_insecure_dev_auth: bool = False

    default_currency: str = "RSD"

    # OIDC (production identity). Empty in local dev.
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""

    @property
    def is_production_like(self) -> bool:
        return self.environment in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
