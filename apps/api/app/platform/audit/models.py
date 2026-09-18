from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.enums import AuditDataClass
from app.common.ids import new_id

# Entries whose school is NULL (platform-level events with no tenant) still
# need a chain to belong to, so they get this reserved key. It cannot collide with
# a real school id, which is always ``org_<ulid>``.
SYSTEM_CHAIN_KEY = "__system__"


class AuditLog(Base, TimestampMixin):
    """Append-only audit trail for relationship / role / payment / document /
    data-request changes. Stores a human summary, never sensitive payloads.

    Entries are **sealed**: each row carries its own SHA-256 digest and the digest
    of the entry before it in the same chain, so the chain is tamper-evident. An
    altered or removed entry breaks every digest after it, which
    :func:`app.platform.audit.service.verify_chain` detects and locates.

    ``UPDATE`` and ``DELETE`` are refused by a database trigger (see the migration
    that introduces ``sequence_no``), so append-only is enforced by the database
    rather than by convention. ``TRUNCATE`` is deliberately still permitted: the
    test harness truncates between tests, and a table owner able to truncate can
    equally drop the table, so that is a backup/restore concern (M21) rather than
    something this port can defend against.

    ``updated_at`` comes from the shared mixin and, on this table, always equals
    ``created_at``: nothing can ever update a row.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_school_created", "school_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
        # One sequence number per chain, which is also what makes a silently
        # re-inserted "replacement" entry impossible to hide.
        UniqueConstraint("chain_key", "sequence_no", name="uq_audit_chain_sequence"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aud"))
    school_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    data_class: Mapped[AuditDataClass] = mapped_column(enum_type(AuditDataClass), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # --- Seal. See app/platform/audit/service.py for how these are computed. ---
    chain_key: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # NULL on exactly one row per chain: the first one.
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Written explicitly rather than by the database, because the digest covers
    # it and both sides have to agree on the value to the microsecond.
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditChainHead(Base, TimestampMixin):
    """The tip of one audit chain: the last sequence number and digest issued.

    Appending locks this row for the chain being written, so two concurrent writes
    in the same school cannot claim the same sequence number or branch the chain.
    The lock is per chain, so schools never block each other.
    """

    __tablename__ = "audit_chain_head"

    chain_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
