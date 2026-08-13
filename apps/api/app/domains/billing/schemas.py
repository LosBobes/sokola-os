from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domains.billing.enums import ChargeCancellationReasonCode, ChargeStatus


class BillingPreviewRequest(BaseModel):
    group_id: str
    # Explicit override, applied to every member. Omit to derive each member's
    # amount from Group.base_monthly_price_minor minus GroupMembership.
    # discount_minor (floored at 0), the normal, pricing-driven path.
    amount_minor: int | None = Field(default=None, gt=0)
    description: str = Field(min_length=1, max_length=200)
    period_label: str = Field(min_length=1, max_length=40)


class BillingPreviewItem(BaseModel):
    person_id: str
    display_name: str
    amount_minor: int


class BillingPreviewResponse(BaseModel):
    preview_hash: str
    currency: str
    total_minor: int
    items: list[BillingPreviewItem]


class PostBillingRunRequest(BillingPreviewRequest):
    # The exact hash from the preview the manager reviewed. If the roster changed
    # in the meantime, the hash won't match and posting is refused.
    preview_hash: str


class BillingRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    description: str
    period_label: str
    currency: str
    total_minor: int
    charge_count: int


class ChargeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    person_id: str
    description: str
    currency: str
    amount_due_minor: int
    amount_paid_minor: int
    status: ChargeStatus
    cancellation_reason: ChargeCancellationReasonCode | None = None
    note: str | None = None


class CancelChargeRequest(BaseModel):
    reason: ChargeCancellationReasonCode
    note: str | None = Field(default=None, max_length=500)


class PersonDebtItem(BaseModel):
    """One person's aggregated outstanding balance (open + partially-paid
    charges only; cancelled charges never contribute)."""

    person_id: str
    display_name: str
    currency: str
    outstanding_minor: int
    open_charge_count: int


class DebtSummaryResponse(BaseModel):
    """Org-wide roll-up of :class:`PersonDebtItem`, the "dugovanja" total."""

    currency: str
    total_outstanding_minor: int
    people_with_debt: int
