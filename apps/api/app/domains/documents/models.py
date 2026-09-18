from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.documents.enums import DocumentType, DocumentVisibility, RetentionPeriod


class Document(Base, TimestampMixin, RecordStatusMixin):
    """An uploaded file's metadata. The bytes themselves live behind
    ``app.domains.documents.storage.StorageBackend``, addressed by
    ``storage_key``, this row is the only thing any other domain, or the API
    surface, ever sees.

    ``created_at`` (from ``TimestampMixin``) doubles as "uploaded at": upload is
    a create-only action, there is no draft state, so the two are always the
    same instant. The API exposes it as ``uploaded_at``.
    """

    __tablename__ = "document"
    __table_args__ = (
        Index("ix_document_school_subject", "school_id", "subject_person_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("doc"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    owner_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    # Who the document is *about*, required when visibility is SUBJECT, and the
    # basis for a guardian's read access to a child's document. Null for
    # STAFF_ONLY documents that aren't about any one person.
    subject_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=True
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    document_type: Mapped[DocumentType] = mapped_column(
        enum_type(DocumentType), nullable=False, default=DocumentType.GENERAL
    )
    visibility: Mapped[DocumentVisibility] = mapped_column(
        enum_type(DocumentVisibility), nullable=False, default=DocumentVisibility.STAFF_ONLY
    )
    retention_period: Mapped[RetentionPeriod | None] = mapped_column(
        enum_type(RetentionPeriod), nullable=True
    )

    # Contract acknowledgement (CONTRACT-type documents only). Both null until
    # the subject (or their guardian) acknowledges.
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
