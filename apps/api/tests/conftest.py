"""Test fixtures. Integration tests run against a real PostgreSQL (the same
throwaway container used in dev). Each test starts from a truncated schema."""

from __future__ import annotations

import os

# Must be set before importing any app module that reads settings / builds the engine.
os.environ.setdefault("SOKOLA_ENVIRONMENT", "test")
os.environ.setdefault(
    "SOKOLA_DATABASE_URL", "postgresql+psycopg://sokola:sokola@localhost:55432/sokola"
)
os.environ.setdefault("SOKOLA_ALLOW_INSECURE_DEV_AUTH", "true")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
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
