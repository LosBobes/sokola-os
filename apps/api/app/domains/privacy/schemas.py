from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.common.enums import RecordStatus
from app.domains.privacy.enums import (
    ConsentScope,
    DataCategory,
    DsarRequestStatus,
    DsarRequestType,
)

# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


class RecordConsentRequest(BaseModel):
    person_id: str = Field(min_length=1)
    scope: ConsentScope
    note: str | None = Field(default=None, max_length=500)


class WithdrawConsentRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ConsentResponse(BaseModel):
    id: str
    person_id: str
    scope: ConsentScope
    granted_at: dt.datetime
    revoked_at: dt.datetime | None
    note: str | None


# ---------------------------------------------------------------------------
# Data-subject requests (DSAR)
# ---------------------------------------------------------------------------


class CreateDsarRequest(BaseModel):
    person_id: str = Field(min_length=1)
    request_type: DsarRequestType
    note: str | None = Field(default=None, max_length=1000)


class DecideDsarRequest(BaseModel):
    """Staff's decision note. Required, a fulfilment/rejection is always
    attested with a reason (v1 has no automated action to point to instead)."""

    note: str = Field(min_length=1, max_length=1000)


class DsarRequestResponse(BaseModel):
    id: str
    person_id: str
    request_type: DsarRequestType
    status: DsarRequestStatus
    note: str | None
    decision_note: str | None
    decided_at: dt.datetime | None
    created_at: dt.datetime


# ---------------------------------------------------------------------------
# Retention periods
# ---------------------------------------------------------------------------


class CreateRetentionPeriodRequest(BaseModel):
    data_category: DataCategory
    retention_period_days: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)


class UpdateRetentionPeriodRequest(BaseModel):
    retention_period_days: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=500)


class RetentionPeriodResponse(BaseModel):
    id: str
    data_category: DataCategory
    retention_period_days: int
    note: str | None
    status: RecordStatus
