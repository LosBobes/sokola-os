from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.common.money import zero
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
    __table_args__ = (
        # M03 §7.2: the composite target another tenant table's foreign key
        # names. It adds no uniqueness — `id` is already the primary key — but
        # it lets a child's reference carry the tenant *as part of the
        # reference*, which is what makes a cross-tenant link impossible rather
        # than merely incorrect.
        UniqueConstraint("school_id", "id", name="uq_billing_run_tenant"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("brn"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    period_label: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[BillingRunStatus] = mapped_column(
        enum_type(BillingRunStatus), nullable=False, default=BillingRunStatus.POSTED
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=zero)
    charge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Charge(Base, TimestampMixin):
    """A debt owed by a person to the school. Money is exact decimal.
    A charge is never edited destructively; it is paid down or cancelled."""

    __tablename__ = "charge"
    __table_args__ = (
        # One reference per school, so a scanned "poziv na broj" resolves to
        # exactly one charge during manual reconciliation.
        Index(
            "uq_charge_payment_reference",
            "school_id",
            "payment_reference",
            unique=True,
            postgresql_where=text("payment_reference IS NOT NULL"),
        ),
        # M03 §7.2: the composite target another tenant table's foreign key
        # names. It adds no uniqueness — `id` is already the primary key — but
        # it lets a child's reference carry the tenant *as part of the
        # reference*, which is what makes a cross-tenant link impossible rather
        # than merely incorrect.
        UniqueConstraint("school_id", "id", name="uq_charge_tenant"),
        # A charge cannot have been posted by another school's billing run.
        ForeignKeyConstraint(
            ["school_id", "billing_run_id"],
            ["billing_run.school_id", "billing_run.id"],
            name="fk_charge_billing_run_tenant",
            ondelete="SET NULL (billing_run_id)",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("chg"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    billing_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[ChargeSourceType] = mapped_column(
        enum_type(ChargeSourceType), nullable=False, default=ChargeSourceType.MANUAL
    )
    status: Mapped[ChargeStatus] = mapped_column(
        enum_type(ChargeStatus), nullable=False, default=ChargeStatus.OPEN
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    # When the money is actually due. Nullable because charges created before
    # this column existed genuinely have no due date, and inventing one would
    # make historical charges look overdue. A charge is "dospelo" only once a
    # due date exists AND has passed, which is why the UI may never print that
    # word without a date beside it.
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # Numeric "poziv na broj" base printed on the slip and encoded in its IPS QR
    # (model + control digits are added at render time, see payments.ips_qr).
    # Stored rather than recomputed so reconciling a bank statement against a
    # reference is an indexed lookup. Nullable for charges predating slips.
    payment_reference: Mapped[str | None] = mapped_column(String(24), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=zero)
    cancellation_reason: Mapped[ChargeCancellationReasonCode | None] = mapped_column(
        enum_type(ChargeCancellationReasonCode), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
