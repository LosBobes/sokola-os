from __future__ import annotations

import enum


class DocumentType(enum.StrEnum):
    """GENERAL is any uploaded file (photo, form, certificate, ...). CONTRACT is
    a subtype that carries an acknowledgement (electronic "I have read/agree")
    state — see ``acknowledged_at``/``acknowledged_by_person_id`` on the model."""

    GENERAL = "GENERAL"
    CONTRACT = "CONTRACT"


class DocumentVisibility(enum.StrEnum):
    """Who — beyond staff, who can always reach anything in their own tenant via
    the DOCUMENTS permission — may see this document.

    STAFF_ONLY: no one outside staff (e.g. internal admin paperwork).
    SUBJECT: the person named in ``subject_person_id`` may see it, and — when
    that subject is a child — so may any guardian with active
    ``GuardianOrganizationAccess`` to that child in this organization. This
    mirrors how the events domain already resolves "which children can this
    parent act for" (see ``app.domains.events.repository.guardian_children``).
    """

    STAFF_ONLY = "STAFF_ONLY"
    SUBJECT = "SUBJECT"


class RetentionPeriod(enum.StrEnum):
    """A declared retention policy label recorded at upload time. Nothing in this
    increment enforces expiry/deletion against it — it is metadata for a future
    retention job, not a guarantee."""

    ONE_YEAR = "ONE_YEAR"
    THREE_YEARS = "THREE_YEARS"
    FIVE_YEARS = "FIVE_YEARS"
    TEN_YEARS = "TEN_YEARS"
    INDEFINITE = "INDEFINITE"
