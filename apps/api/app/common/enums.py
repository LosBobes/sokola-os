"""Cross-cutting enums shared by every domain.

Domain-specific enums live next to their models. Only genuinely shared status
vocabularies belong here.
"""

from __future__ import annotations

import enum


class RecordStatus(enum.StrEnum):
    """Soft-lifecycle marker present on most tenant rows.

    We never hard-delete business records; we transition them. ``ARCHIVED`` hides
    a row from normal reads while preserving history and audit lineage.
    """

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class AuditDataClass(enum.StrEnum):
    """Sensitivity class attached to every audit entry."""

    IDENTITY = "IDENTITY"
    RELATIONSHIP = "RELATIONSHIP"
    ROLE = "ROLE"
    FINANCIAL = "FINANCIAL"
    DOCUMENT = "DOCUMENT"
    DATA_REQUEST = "DATA_REQUEST"
    OPERATIONAL = "OPERATIONAL"
