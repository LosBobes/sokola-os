from __future__ import annotations

import enum


class PaymentRecordStatus(enum.StrEnum):
    RECORDED = "RECORDED"
    VOIDED = "VOIDED"


class PaymentMethod(enum.StrEnum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD_EXTERNAL = "CARD_EXTERNAL"
    OTHER = "OTHER"


class PaymentVoidReasonCode(enum.StrEnum):
    ERROR = "ERROR"
    REFUNDED = "REFUNDED"
    DUPLICATE = "DUPLICATE"
    OTHER = "OTHER"
