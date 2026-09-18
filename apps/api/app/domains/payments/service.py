from __future__ import annotations

from sqlalchemy.orm import Session

from app.common import money
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

    outstanding = charge.amount_due - charge.amount_paid
    if outstanding <= 0:
        raise ConflictError("Zaduženje je već izmireno.")
    if req.amount > outstanding:
        raise ConflictError(
            "Iznos uplate premašuje preostali dug.",
            # The wire format, like every other amount the API emits: a raw
            # Decimal is not JSON-serialisable and would turn a 409 into a 500.
            details={"code": "OVERPAYMENT", "outstanding": money.format_amount(outstanding)},
        )

    payment = PaymentRecord(
        organization_id=context.organization_id,
        charge_id=charge_id,
        amount=req.amount,
        currency=charge.currency,
        method=req.method,
    )
    db.add(payment)

    charge.amount_paid += req.amount
    charge.status = (
        ChargeStatus.PAID
        if charge.amount_paid >= charge.amount_due
        else ChargeStatus.PARTIALLY_PAID
    )
    db.flush()

    result = PaymentResponse(
        id=payment.id,
        charge_id=charge_id,
        amount=payment.amount,
        currency=payment.currency,
        method=payment.method,
        status=payment.status,
        charge_status=charge.status,
        charge_amount_due=charge.amount_due,
        charge_amount_paid=charge.amount_paid,
    )
    record_audit(
        db,
        data_class=AuditDataClass.FINANCIAL,
        action="payment.recorded",
        entity_type="charge",
        entity_id=charge_id,
        summary=f"Evidentirana uplata {req.amount} ({req.method}).",
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
    subtracted back out of the charge's ``amount_paid`` and the charge's
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

    charge.amount_paid = max(charge.amount_paid - payment.amount, money.zero())
    if charge.status is not ChargeStatus.CANCELLED:
        if charge.amount_paid <= 0:
            charge.status = ChargeStatus.OPEN
        elif charge.amount_paid < charge.amount_due:
            charge.status = ChargeStatus.PARTIALLY_PAID
        else:
            charge.status = ChargeStatus.PAID

    payment.status = PaymentRecordStatus.VOIDED
    payment.void_reason = req.reason
    db.flush()

    result = PaymentResponse(
        id=payment.id,
        charge_id=payment.charge_id,
        amount=payment.amount,
        currency=payment.currency,
        method=payment.method,
        status=payment.status,
        charge_status=charge.status,
        charge_amount_due=charge.amount_due,
        charge_amount_paid=charge.amount_paid,
    )
    record_audit(
        db,
        data_class=AuditDataClass.FINANCIAL,
        action="payment.voided",
        entity_type="charge",
        entity_id=charge.id,
        summary=f"Poništena uplata {payment.amount} ({req.reason.value}).",
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
