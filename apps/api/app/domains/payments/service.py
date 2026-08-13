from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, NotFoundError
from app.domains.billing.enums import ChargeStatus
from app.domains.payments import repository
from app.domains.payments.enums import PaymentRecordStatus
from app.domains.payments.models import PaymentRecord
from app.domains.payments.schemas import PaymentResponse, RecordPaymentRequest, VoidPaymentRequest
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def record_payment(
    db: Session,
    context: RequestContext,
    charge_id: str,
    req: RecordPaymentRequest,
    idempotency_key: str | None,
) -> PaymentResponse:
    """Journey 6. Record an external payment against a charge. Ledger semantics:
    partial → PARTIALLY_PAID, full → PAID, overpayment rejected. Idempotent."""
    params = {"charge_id": charge_id, **req.model_dump()}
    guard = None
    if idempotency_key:
        guard = idempotency.begin(
            db, context.organization_id, "payments.record", idempotency_key, params
        )
        if guard.replay is not None:
            return PaymentResponse.model_validate(guard.replay["body"])

    charge = repository.get_charge_for_update(db, context.organization_id, charge_id)
    if charge is None:
        raise NotFoundError("Zaduženje nije pronađeno.")
    if charge.status is ChargeStatus.CANCELLED:
        raise ConflictError("Zaduženje je otkazano; uplata nije moguća.")

    outstanding = charge.amount_due_minor - charge.amount_paid_minor
    if outstanding <= 0:
        raise ConflictError("Zaduženje je već izmireno.")
    if req.amount_minor > outstanding:
        raise ConflictError(
            "Iznos uplate premašuje preostali dug.",
            details={"code": "OVERPAYMENT", "outstanding_minor": outstanding},
        )

    payment = PaymentRecord(
        organization_id=context.organization_id,
        charge_id=charge_id,
        amount_minor=req.amount_minor,
        currency=charge.currency,
        method=req.method,
    )
    db.add(payment)

    charge.amount_paid_minor += req.amount_minor
    charge.status = (
        ChargeStatus.PAID
        if charge.amount_paid_minor >= charge.amount_due_minor
        else ChargeStatus.PARTIALLY_PAID
    )
    db.flush()

    result = PaymentResponse(
        id=payment.id,
        charge_id=charge_id,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        method=payment.method,
        status=payment.status,
        charge_status=charge.status,
        charge_amount_due_minor=charge.amount_due_minor,
        charge_amount_paid_minor=charge.amount_paid_minor,
    )
    record_audit(
        db,
        data_class=AuditDataClass.FINANCIAL,
        action="payment.recorded",
        entity_type="charge",
        entity_id=charge_id,
        summary=f"Evidentirana uplata {req.amount_minor} ({req.method}).",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="payment.recorded",
        payload={
            "payment_id": payment.id,
            "charge_id": charge_id,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )
    if guard is not None:
        idempotency.complete(db, guard, status=201, body=result.model_dump(mode="json"))
    db.commit()
    return result


def void_payment(
    db: Session,
    context: RequestContext,
    payment_id: str,
    req: VoidPaymentRequest,
    idempotency_key: str | None,
) -> PaymentResponse:
    """PRD 07 P2. Reverses a recorded payment: the amount it applied is
    subtracted back out of the charge's ``amount_paid_minor`` and the charge's
    status is recomputed from what remains. A CANCELLED charge stays
    CANCELLED, cancellation is terminal regardless of the ledger."""
    params = {"payment_id": payment_id, **req.model_dump()}
    guard = None
    if idempotency_key:
        guard = idempotency.begin(
            db, context.organization_id, "payments.void", idempotency_key, params
        )
        if guard.replay is not None:
            return PaymentResponse.model_validate(guard.replay["body"])

    payment = repository.get_payment_for_update(db, context.organization_id, payment_id)
    if payment is None:
        raise NotFoundError("Uplata nije pronađena.")
    if payment.status is PaymentRecordStatus.VOIDED:
        raise ConflictError("Uplata je već poništena.")

    charge = repository.get_charge_for_update(db, context.organization_id, payment.charge_id)
    if charge is None:
        raise NotFoundError("Zaduženje nije pronađeno.")

    charge.amount_paid_minor = max(charge.amount_paid_minor - payment.amount_minor, 0)
    if charge.status is not ChargeStatus.CANCELLED:
        if charge.amount_paid_minor <= 0:
            charge.status = ChargeStatus.OPEN
        elif charge.amount_paid_minor < charge.amount_due_minor:
            charge.status = ChargeStatus.PARTIALLY_PAID
        else:
            charge.status = ChargeStatus.PAID

    payment.status = PaymentRecordStatus.VOIDED
    payment.void_reason = req.reason
    db.flush()

    result = PaymentResponse(
        id=payment.id,
        charge_id=payment.charge_id,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        method=payment.method,
        status=payment.status,
        charge_status=charge.status,
        charge_amount_due_minor=charge.amount_due_minor,
        charge_amount_paid_minor=charge.amount_paid_minor,
    )
    record_audit(
        db,
        data_class=AuditDataClass.FINANCIAL,
        action="payment.voided",
        entity_type="charge",
        entity_id=charge.id,
        summary=f"Poništena uplata {payment.amount_minor} ({req.reason.value}).",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="payment.voided",
        payload={
            "payment_id": payment.id,
            "charge_id": charge.id,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )
    if guard is not None:
        idempotency.complete(db, guard, status=200, body=result.model_dump(mode="json"))
    db.commit()
    return result
