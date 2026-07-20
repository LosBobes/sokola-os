from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.privacy.enums import (
    ConsentScope,
    DataCategory,
    DsarRequestStatus,
    DsarRequestType,
)


class ConsentRecord(Base, TimestampMixin):
    """One person's consent for one processing purpose, in one organization.

    Consents are never deleted or edited in place — withdrawal sets
    ``revoked_at`` and the row stays as evidence of what was once granted and
    when it stopped applying.
    """

    __tablename__ = "privacy_consent_record"
    __table_args__ = (
        Index("ix_privacy_consent_record_org_person", "organization_id", "person_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("csn"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[ConsentScope] = mapped_column(enum_type(ConsentScope), nullable=False)
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DataSubjectRequest(Base, TimestampMixin):
    """A data-subject access/export/erasure request (DSAR), tracked from
    intake to decision.

    v1 fulfilment is deliberately conservative: staff mark a request
    FULFILLED/REJECTED with a note (``decision_note``). No automated data
    export or erasure runs off this row — that is a larger, separate effort
    (see the PR description's scope cuts).
    """

    __tablename__ = "privacy_data_subject_request"
    __table_args__ = (
        Index("ix_privacy_dsar_org_person", "organization_id", "person_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("dsr"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    request_type: Mapped[DsarRequestType] = mapped_column(
        enum_type(DsarRequestType), nullable=False
    )
    status: Mapped[DsarRequestStatus] = mapped_column(
        enum_type(DsarRequestStatus), nullable=False, default=DsarRequestStatus.PENDING
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetentionPeriod(Base, TimestampMixin, RecordStatusMixin):
    """How long one category of data is kept, per organization.

    Data model only — no automated expiry/purge job runs against this yet;
    that is a follow-up (see the PR description's scope cuts).
    """

    __tablename__ = "privacy_retention_period"
    __table_args__ = (Index("ix_privacy_retention_period_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rtp"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    data_category: Mapped[DataCategory] = mapped_column(enum_type(DataCategory), nullable=False)
    retention_period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
