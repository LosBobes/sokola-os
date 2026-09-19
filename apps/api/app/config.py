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

# Fixed, published, and therefore worthless as secrets. They exist so a fresh
# checkout runs without setup; ``_guard_contact_keys`` refuses them outside
# local/test, and the word "insecure" in the material is what it looks for.
_DEV_INSECURE_KEY = "ZGV2LWluc2VjdXJlLWNvbnRhY3Qta2V5LS1jaGFuZ2U="
_DEV_INSECURE_FINGERPRINT_KEY = "ZGV2LWluc2VjdXJlLWZwLWtleS0tLS0tLS1jaGFuZ2U="


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

    # --- Auth session. The server-side `auth_session` row is the session
    # (M01 §3.2); the signed cookie only carries its opaque credential, so the
    # secret still has to change outside local. ---
    session_secret: str = "dev-insecure-session-secret-change-me"
    # M01 §3.2's fail-closed defaults, and the spec is emphatic that these are
    # "strukturirana bezbednosna konfiguracija, ne dokumentaciona pretpostavka":
    # a session ends after 30 minutes idle or 12 hours absolute, whichever comes
    # first. Raising either is a deliberate, audited security decision.
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12

    # --- Google OIDC. When client id + secret are set, the Google login flow
    # is enabled; otherwise the app falls back to the dev header adapter. ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_discovery_url: str = "https://accounts.google.com/.well-known/openid-configuration"
    # Must exactly match an authorized redirect URI in the Google OAuth client.
    oidc_redirect_url: str = "http://localhost:5173/api/auth/google/callback"
    # Where the browser lands after a successful login.
    web_post_login_url: str = "http://localhost:5173/"

    # --- Email + password login (M01 §4.9). Off by default, and the default is
    # the point: "Ne postoji local fallback login... ako za njega nema
    # eksplicitnog adaptera, konfiguracije i testova. Podrazumevano je OFF."
    # All three exist here (`app/security/password_auth.py`,
    # `SOKOLA_PASSWORD_AUTH_ENABLED`, `tests/test_password_auth.py`), so the
    # method is permitted — but a deployment that never said yes has not said
    # yes, and a sign-in method that appears because nobody turned it off is the
    # shape of every accidental auth surface. `compose.prod.yml` passes an
    # explicit `true`, so this changes no running deployment.
    password_auth_enabled: bool = False
    # Server-side pepper folded into every password hash (see
    # app.security.password). Held only in the environment, never in the DB.
    # Change it outside local, and note that changing it invalidates every
    # existing password hash (users must reset), so rotate deliberately.
    password_pepper: str = "dev-insecure-password-pepper-change-me"

    # --- Contact protection (M04 §2.0). Two independent keyrings, each
    # "<version>:<base64 32-byte key>" entries separated by commas; the highest
    # version is the one new values are written under, older versions stay
    # readable so a rotation needs no re-encryption. Encryption and fingerprint
    # keys are separate on purpose: one protects confidentiality, the other makes
    # dedupe possible, and they are rotated for different reasons. Both are
    # dev-only defaults here and refused in staging/production (see app.main).
    # See app.platform.crypto.generate_key to mint a real one. ---
    contact_encryption_keys: str = "1:" + _DEV_INSECURE_KEY
    contact_fingerprint_keys: str = "1:" + _DEV_INSECURE_FINGERPRINT_KEY

    @property
    def is_production_like(self) -> bool:
        return self.environment in ("staging", "production")

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
