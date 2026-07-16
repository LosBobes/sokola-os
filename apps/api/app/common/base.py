"""Declarative base and shared column mixins.

``Base`` is the single metadata object Alembic autogenerates against. Every
model imported before ``target_metadata`` is read participates in migrations.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.common.columns import enum_type
from app.common.enums import RecordStatus


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RecordStatusMixin:
    record_status: Mapped[RecordStatus] = mapped_column(
        enum_type(RecordStatus), default=RecordStatus.ACTIVE, nullable=False
    )
