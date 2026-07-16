from __future__ import annotations

import enum


class BillingRunStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class ChargeStatus(enum.StrEnum):
    OPEN = "OPEN"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class ChargeSourceType(enum.StrEnum):
    MEMBERSHIP = "MEMBERSHIP"
    EVENT = "EVENT"
    MANUAL = "MANUAL"
    OTHER = "OTHER"


class ChargeCancellationReasonCode(enum.StrEnum):
    WAIVED = "WAIVED"
    ERROR = "ERROR"
    DUPLICATE = "DUPLICATE"
    OTHER = "OTHER"
