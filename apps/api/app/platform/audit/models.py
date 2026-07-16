from __future__ import annotations

from typing import Any

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.enums import AuditDataClass
from app.common.ids import new_id


class AuditLog(Base, TimestampMixin):
    """Append-only audit trail for relationship / role / payment / document /
    data-request changes. Stores a human summary, never sensitive payloads."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_org_created", "organization_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aud"))
    organization_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    data_class: Mapped[AuditDataClass] = mapped_column(enum_type(AuditDataClass), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
