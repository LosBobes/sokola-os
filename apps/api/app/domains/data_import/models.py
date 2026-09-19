from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.data_import.enums import (
    ImportBatchStatus,
    ImportRowCommitStatus,
    ImportRowValidationStatus,
)


class ImportBatch(Base, TimestampMixin):
    """One uploaded CSV file, staged for review before it touches real data.

    The audit trail for a bulk import: who ran it (``created_by_person_id``),
    when (``created_at`` from :class:`TimestampMixin`, plus ``previewed_at`` /
    ``committed_at``), and the row-count summary at each stage. Rows themselves
    live in :class:`ImportRow`, staged separately from the source file (v1
    stores parsed rows, not the raw upload, see the service module docstring).
    """

    __tablename__ = "import_batch"
    __table_args__ = (
        # M03 §7.2: the composite target another tenant table's foreign key
        # names. It adds no uniqueness — `id` is already the primary key — but
        # it lets a child's reference carry the tenant *as part of the
        # reference*, which is what makes a cross-tenant link impossible rather
        # than merely incorrect.
        UniqueConstraint("school_id", "id", name="uq_import_batch_tenant"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("imb"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ImportBatchStatus] = mapped_column(
        enum_type(ImportBatchStatus), nullable=False, default=ImportBatchStatus.PENDING
    )
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_person_id: Mapped[str] = mapped_column(String(64), nullable=False)

    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    previewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    committed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImportRow(Base, TimestampMixin):
    """One staged CSV data row, parsed at upload time and re-checked on every
    preview. ``school_id`` is denormalized from the parent batch so this
    table's own tenant-isolation queries never need a join."""

    __tablename__ = "import_row"
    __table_args__ = (
        # `school_id` here is denormalized from the batch (see the docstring),
        # and this is what keeps the two honest: a row cannot belong to a batch
        # of a different school. §7.3.
        ForeignKeyConstraint(
            ["school_id", "batch_id"],
            ["import_batch.school_id", "import_batch.id"],
            name="fk_import_row_batch_tenant",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("imr"))
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Raw (trimmed) values as read from the CSV, the fixed v1 header, see
    # app.domains.data_import.service.REQUIRED_COLUMNS / OPTIONAL_COLUMNS.
    given_name: Mapped[str] = mapped_column(String(120), nullable=False)
    family_name: Mapped[str] = mapped_column(String(120), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    local_member_code: Mapped[str | None] = mapped_column(String(60), nullable=True)

    validation_status: Mapped[ImportRowValidationStatus] = mapped_column(
        enum_type(ImportRowValidationStatus),
        nullable=False,
        default=ImportRowValidationStatus.PENDING,
    )
    validation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Existing people in this org whose name looks like a match (§6-style
    # duplicate detection), informational, never makes a row invalid.
    duplicate_person_ids: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(64)), nullable=True
    )

    commit_status: Mapped[ImportRowCommitStatus] = mapped_column(
        enum_type(ImportRowCommitStatus), nullable=False, default=ImportRowCommitStatus.PENDING
    )
    commit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
