"""Test fixtures. Integration tests run against a real PostgreSQL, the same
throwaway container used in dev, but a DEDICATED `sokola_test` database within
it, never the `sokola` database dev actually works in. Each test starts from a
truncated schema, so pointing this at a shared database would destroy live
data on every single test run (it did once, see git history)."""

from __future__ import annotations

import os

# Must be set before importing any app module that reads settings / builds the engine.
os.environ.setdefault("SOKOLA_ENVIRONMENT", "test")
os.environ.setdefault(
    "SOKOLA_DATABASE_URL", "postgresql+psycopg://sokola:sokola@localhost:55432/sokola_test"
)
os.environ.setdefault("SOKOLA_ALLOW_INSECURE_DEV_AUTH", "true")
# M01 §4.9: the local password adapter is off unless a deployment says yes.
# The test suite is such a deployment — it exercises the adapter — so it says so
# out loud rather than relying on a default, which is the same reason
# `compose.prod.yml` passes an explicit value.
os.environ.setdefault("SOKOLA_PASSWORD_AUTH_ENABLED", "true")
# Tests must not silently inherit real Google credentials from a developer's
# local .env, pin these off so google_enabled is deterministic.
os.environ.setdefault("SOKOLA_GOOGLE_CLIENT_ID", "")
os.environ.setdefault("SOKOLA_GOOGLE_CLIENT_SECRET", "")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.domains.authorization.registry import ensure_policy_revision  # noqa: E402
from app.domains.identity.auth_providers import ensure_builtin_providers  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models_registry import Base  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    if tables:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    # The M01 provider registry is reference data, seeded by its migration and
    # by `sync_provider_registry` at boot. TRUNCATE takes it with everything
    # else, and an `auth_identity` cannot exist without it, so put it back.
    with SessionLocal() as session:
        ensure_builtin_providers(session)
        # The M05 policy registry is reference data too, published by its
        # migration. TRUNCATE takes it with everything else, and an
        # authorization decision cannot be made without it.
        ensure_policy_revision(session)
        session.commit()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client
