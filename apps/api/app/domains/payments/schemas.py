from __future__ import annotations

from pydantic import BaseModel, Field

from app.domains.billing.enums import ChargeStatus
from app.domains.payments.enums import PaymentMethod, PaymentRecordStatus, PaymentVoidReasonCode


class RecordPaymentRequest(BaseModel):
    amount_minor: int = Field(gt=0)
    method: PaymentMethod


class PaymentResponse(BaseModel):
    id: str
    charge_id: str
    amount_minor: int
    currency: str
    method: PaymentMethod
    status: PaymentRecordStatus
    # The charge's resulting ledger state, so the client needn't re-fetch.
    charge_status: ChargeStatus
    charge_amount_due_minor: int
    charge_amount_paid_minor: int


class VoidPaymentRequest(BaseModel):
    reason: PaymentVoidReasonCode
