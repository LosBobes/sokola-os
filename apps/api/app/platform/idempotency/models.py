from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.platform.idempotency.enums import IdempotencyStatus


class IdempotencyRecord(Base, TimestampMixin):
    """One row per (school, operation, client key).

    Guarantees: repeated request + same key -> same stored result; same key +
    different parameters -> rejected. Scoped per school so keys never leak
    across tenants.
    """

    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint(
            "school_id", "operation", "idempotency_key", name="uq_idempotency_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("idm"))
    school_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[IdempotencyStatus] = mapped_column(
        enum_type(IdempotencyStatus), nullable=False, default=IdempotencyStatus.IN_PROGRESS
    )
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A JSON response body, may be an object or an array.
    response_body: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
