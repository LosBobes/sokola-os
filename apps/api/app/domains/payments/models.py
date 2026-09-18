from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.payments.enums import PaymentMethod, PaymentRecordStatus, PaymentVoidReasonCode


class PaymentRecord(Base, TimestampMixin):
    """A ledger entry recording money received against a charge. This is an
    external-payment *record*, not a gateway capture. It is voidable but never
    edited in place; corrections are new records."""

    __tablename__ = "payment_record"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pay"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    charge_id: Mapped[str] = mapped_column(
        ForeignKey("charge.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(enum_type(PaymentMethod), nullable=False)
    status: Mapped[PaymentRecordStatus] = mapped_column(
        enum_type(PaymentRecordStatus), nullable=False, default=PaymentRecordStatus.RECORDED
    )
    void_reason: Mapped[PaymentVoidReasonCode | None] = mapped_column(
        enum_type(PaymentVoidReasonCode), nullable=True
    )
