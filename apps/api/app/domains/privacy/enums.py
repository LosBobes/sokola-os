"""Privacy domain enums (PRD 12): consents, data-subject requests (DSAR), and
retention periods."""

from __future__ import annotations

import enum


class ConsentScope(enum.StrEnum):
    """What a consent covers — a closed vocabulary of processing purposes a
    person may grant or withdraw, independent of any one domain's own
    feature set."""

    DATA_PROCESSING = "DATA_PROCESSING"
    MARKETING_COMMUNICATIONS = "MARKETING_COMMUNICATIONS"
    PHOTO_VIDEO = "PHOTO_VIDEO"
    THIRD_PARTY_SHARING = "THIRD_PARTY_SHARING"


class DsarRequestType(enum.StrEnum):
    ACCESS = "ACCESS"
    EXPORT = "EXPORT"
    ERASURE = "ERASURE"


class DsarRequestStatus(enum.StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    FULFILLED = "FULFILLED"
    REJECTED = "REJECTED"


class DataCategory(enum.StrEnum):
    """A category of stored personal data a retention period can be attached
    to. Deliberately domain-agnostic — one category may span several
    domains' tables (e.g. DOCUMENTS covers files across the product)."""

    PERSONAL_PROFILE = "PERSONAL_PROFILE"
    ATTENDANCE_RECORDS = "ATTENDANCE_RECORDS"
    BILLING_RECORDS = "BILLING_RECORDS"
    DOCUMENTS = "DOCUMENTS"
    COMMUNICATIONS = "COMMUNICATIONS"
    MEDIA = "MEDIA"
