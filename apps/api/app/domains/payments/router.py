from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.http import IdempotencyKey
from app.domains.payments import service
from app.domains.payments.schemas import PaymentResponse, RecordPaymentRequest, VoidPaymentRequest
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["payments"])

_finance = require_permission(PermissionArea.PAYMENTS)
FinanceContext = Annotated[ContextDep, Depends(_finance)]


@router.post(
    "/charges/{charge_id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="recordPayment",
    responses={409: {"description": "Overpayment, already settled, or cancelled charge."}},
)
def record_payment(
    charge_id: str,
    body: RecordPaymentRequest,
    db: DbDep,
    context: FinanceContext,
    idempotency_key: IdempotencyKey = None,
) -> PaymentResponse:
    return service.record_payment(db, context, charge_id, body, idempotency_key)


@router.post(
    "/payments/{payment_id}/void",
    response_model=PaymentResponse,
    operation_id="voidPayment",
    responses={409: {"description": "Payment already voided."}},
)
def void_payment(
    payment_id: str,
    body: VoidPaymentRequest,
    db: DbDep,
    context: FinanceContext,
    idempotency_key: IdempotencyKey = None,
) -> PaymentResponse:
    return service.void_payment(db, context, payment_id, body, idempotency_key)
