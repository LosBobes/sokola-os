from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.http import IdempotencyKey
from app.domains.identity.enums import RoleCode
from app.domains.payments import service
from app.domains.payments.schemas import PaymentResponse, RecordPaymentRequest
from app.security.deps import ContextDep, DbDep, require_roles

router = APIRouter(tags=["payments"])

_finance = require_roles(RoleCode.OWNER, RoleCode.MANAGER, RoleCode.ADMIN)
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
