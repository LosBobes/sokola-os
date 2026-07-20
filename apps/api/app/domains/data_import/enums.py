from __future__ import annotations

import enum


class ImportBatchStatus(enum.StrEnum):
    """Lifecycle of one uploaded CSV file.

    ``PENDING`` -> rows are staged, not yet validated. ``PREVIEWED`` -> every
    row has been checked (dry-run) and the batch may be committed. ``COMMITTED``
    is terminal: a batch can be committed at most once (§ import v1 — no
    rollback, see service module docstring).
    """

    PENDING = "PENDING"
    PREVIEWED = "PREVIEWED"
    COMMITTED = "COMMITTED"


class ImportRowValidationStatus(enum.StrEnum):
    """Result of the dry-run check for one staged row."""

    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"


class ImportRowCommitStatus(enum.StrEnum):
    """Result of actually applying one staged row during commit."""

    PENDING = "PENDING"
    CREATED = "CREATED"
    SKIPPED = "SKIPPED"
