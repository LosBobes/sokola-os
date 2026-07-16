from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.billing.enums import (
    BillingRunStatus,
    ChargeCancellationReasonCode,
    ChargeSourceType,
    ChargeStatus,
)


class BillingRun(Base, TimestampMixin):
    """A posted batch of charges. Charges are generated atomically when the run is
    posted, from a preview the manager reviewed."""

    __tablename__ = "billing_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("brn"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    period_label: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[BillingRunStatus] = mapped_column(
        enum_type(BillingRunStatus), nullable=False, default=BillingRunStatus.POSTED
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    charge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Charge(Base, TimestampMixin):
    """A debt owed by a person to the organization. Money is integer minor units.
    A charge is never edited destructively; it is paid down or cancelled."""

    __tablename__ = "charge"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("chg"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    billing_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("billing_run.id", ondelete="SET NULL"), nullable=True
    )
    source_type: Mapped[ChargeSourceType] = mapped_column(
        enum_type(ChargeSourceType), nullable=False, default=ChargeSourceType.MANUAL
    )
    status: Mapped[ChargeStatus] = mapped_column(
        enum_type(ChargeStatus), nullable=False, default=ChargeStatus.OPEN
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_due_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancellation_reason: Mapped[ChargeCancellationReasonCode | None] = mapped_column(
        enum_type(ChargeCancellationReasonCode), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
