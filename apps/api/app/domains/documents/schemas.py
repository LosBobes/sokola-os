from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from app.domains.documents.enums import DocumentType, DocumentVisibility, RetentionPeriod


class DocumentResponse(BaseModel):
    id: str
    school_id: str
    owner_person_id: str
    subject_person_id: str | None
    filename: str
    content_type: str
    size_bytes: int
    document_type: DocumentType
    visibility: DocumentVisibility
    retention_period: RetentionPeriod | None
    uploaded_at: dt.datetime
    acknowledged_at: dt.datetime | None
    acknowledged_by_person_id: str | None
