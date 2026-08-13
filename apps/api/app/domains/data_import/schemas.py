from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domains.data_import.enums import ImportBatchStatus


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: ImportBatchStatus
    source_filename: str
    created_by_person_id: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created_rows: int
    skipped_rows: int
    created_at: dt.datetime
    previewed_at: dt.datetime | None
    committed_at: dt.datetime | None


class ImportRowPreviewResult(BaseModel):
    """One row's dry-run outcome. ``valid`` and ``duplicate_person_ids`` are
    independent, a row can be valid AND look like an existing person; the
    caller decides whether that's acceptable (v1 never blocks on it)."""

    row_number: int
    given_name: str
    family_name: str
    group_name: str | None
    local_member_code: str | None
    valid: bool
    reason: str | None
    duplicate_person_ids: list[str]


class ImportPreviewResponse(BaseModel):
    batch: ImportBatchResponse
    rows: list[ImportRowPreviewResult]


class ImportRowCommitResult(BaseModel):
    row_number: int
    given_name: str
    family_name: str
    outcome: Literal["CREATED", "SKIPPED"]
    reason: str | None
    person_id: str | None


class ImportCommitResponse(BaseModel):
    batch: ImportBatchResponse
    rows: list[ImportRowCommitResult]
