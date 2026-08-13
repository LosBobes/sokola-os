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

    # --- Document storage. Local filesystem only in this increment (no object
    # store credentials available); relative paths resolve against the process
    # cwd (apps/api in dev/CI). Gitignored, a runtime cache, not source of
    # truth (the `document` table row is). See app/domains/documents/storage.py
    # for the interface a future S3/GCS backend would implement instead. ---
    documents_storage_dir: str = "var/documents"

    # --- Auth session (signed cookie). Change the secret outside local. ---
    session_secret: str = "dev-insecure-session-secret-change-me"

    # --- Google OIDC. When client id + secret are set, the Google login flow
    # is enabled; otherwise the app falls back to the dev header adapter. ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_discovery_url: str = "https://accounts.google.com/.well-known/openid-configuration"
    # Must exactly match an authorized redirect URI in the Google OAuth client.
    oidc_redirect_url: str = "http://localhost:5173/api/auth/google/callback"
    # Where the browser lands after a successful login.
    web_post_login_url: str = "http://localhost:5173/"

    # --- Email + password login. On by default: a user can register and sign
    # in with just an email and password, no external provider or email link. ---
    password_auth_enabled: bool = True
    # Server-side pepper folded into every password hash (see
    # app.security.password). Held only in the environment, never in the DB.
    # Change it outside local, and note that changing it invalidates every
    # existing password hash (users must reset), so rotate deliberately.
    password_pepper: str = "dev-insecure-password-pepper-change-me"

    @property
    def is_production_like(self) -> bool:
        return self.environment in ("staging", "production")

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
