"""Database engine, session factory, and the declarative base.

Sync SQLAlchemy 2.0 is used deliberately: it makes transaction boundaries,
``SELECT ... FOR UPDATE`` locking, and the outbox/idempotency patterns explicit
and easy to test. FastAPI runs sync endpoints in a threadpool.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session.

    The session is rolled back and closed at the end of the request. Endpoints
    commit explicitly so an uncommitted mutation never leaks a side effect.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
