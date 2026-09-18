from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.billing.models import Charge
from app.domains.payments.models import PaymentRecord


def get_charge_for_update(db: Session, school_id: str, charge_id: str) -> Charge | None:
    """Lock the charge row so concurrent payments serialize and can't both spend
    the same outstanding balance."""
    stmt = (
        select(Charge)
        .where(Charge.id == charge_id, Charge.school_id == school_id)
        .with_for_update()
    )
    return db.execute(stmt).scalar_one_or_none()


def get_payment_for_update(
    db: Session, school_id: str, payment_id: str
) -> PaymentRecord | None:
    """Lock the payment row so it can't be voided twice concurrently."""
    stmt = (
        select(PaymentRecord)
        .where(PaymentRecord.id == payment_id, PaymentRecord.school_id == school_id)
        .with_for_update()
    )
    return db.execute(stmt).scalar_one_or_none()
