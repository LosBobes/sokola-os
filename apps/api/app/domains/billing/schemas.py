from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domains.billing.enums import ChargeStatus


class BillingPreviewRequest(BaseModel):
    group_id: str
    amount_minor: int = Field(gt=0)
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
