"""Document upload/download/acknowledge business logic.

Authorization has two independent layers, mirroring the events domain's staff
vs. parent split:

* Write paths that only staff may reach (upload, listing every document in the
  tenant) are gated at the router with ``require_permission(DOCUMENTS)``.
* Resource-level access (can THIS caller see/download/acknowledge THIS
  document) is re-checked here against ``school_id`` and
  ``visibility`` regardless of role, a staff member's DOCUMENTS grant always
  passes it; anyone else passes only for their own or their guarded child's
  SUBJECT-visibility documents. Never trust the client for either.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import BadRequestError, ForbiddenError, NotFoundError
from app.common.pagination import Page, PageParams
from app.config import get_settings
from app.domains.documents import repository
from app.domains.documents.enums import DocumentType, DocumentVisibility, RetentionPeriod
from app.domains.documents.models import Document
from app.domains.documents.schemas import DocumentResponse
from app.domains.documents.storage import LocalFilesystemBackend, StorageBackend
from app.platform import clock
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext
from app.security.permissions import PermissionArea, effective_areas, parse_granted_areas

# Allowlisted upload formats (issue #11): pdf, jpg, png, docx. Reject anything
# else with a Serbian error rather than silently accepting arbitrary bytes.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": "PDF",
    "image/jpeg": "JPG",
    "image/png": "PNG",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


@dataclasses.dataclass(frozen=True, slots=True)
class DocumentContent:
    filename: str
    content_type: str
    data: bytes


def _storage() -> StorageBackend:
    # Local-filesystem only for this increment (see storage.py docstring for the
    # S3/GCS swap-in note). A future backend just replaces this one line.
    return LocalFilesystemBackend(get_settings().documents_storage_dir)


def _now() -> dt.datetime:
    return clock.now()


def _has_documents_permission(context: RequestContext) -> bool:
    granted = parse_granted_areas(context.granted_areas)
    return PermissionArea.DOCUMENTS in effective_areas(context.role_code, granted)


def _can_view(db: Session, context: RequestContext, document: Document) -> bool:
    if _has_documents_permission(context):
        return True
    if document.visibility is not DocumentVisibility.SUBJECT or document.subject_person_id is None:
        return False
    if document.subject_person_id == context.person_id:
        return True
    return document.subject_person_id in repository.guardian_child_ids(
        db, context.school_id, context.person_id
    )


def _load_authorized(db: Session, context: RequestContext, document_id: str) -> Document:
    document = repository.get_document(db, context.school_id, document_id)
    if document is None:
        raise NotFoundError("Dokument nije pronađen.")
    if not _can_view(db, context, document):
        raise ForbiddenError("Nemate pravo pristupa ovom dokumentu.")
    return document


def _to_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        school_id=document.school_id,
        owner_person_id=document.owner_person_id,
        subject_person_id=document.subject_person_id,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        document_type=document.document_type,
        visibility=document.visibility,
        retention_period=document.retention_period,
        uploaded_at=document.created_at,
        acknowledged_at=document.acknowledged_at,
        acknowledged_by_person_id=document.acknowledged_by_person_id,
    )


def upload_document(
    db: Session,
    context: RequestContext,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    document_type: DocumentType,
    visibility: DocumentVisibility,
    subject_person_id: str | None,
    retention_period: RetentionPeriod | None,
) -> DocumentResponse:
    if content_type not in ALLOWED_CONTENT_TYPES:
        allowed = ", ".join(ALLOWED_CONTENT_TYPES.values())
        raise BadRequestError(
            f"Format fajla nije podržan. Dozvoljeni formati: {allowed}.",
            details={"code": "UNSUPPORTED_FORMAT"},
        )
    if not data:
        raise BadRequestError("Fajl je prazan.", details={"code": "EMPTY_FILE"})
    if len(data) > MAX_UPLOAD_SIZE_BYTES:
        raise BadRequestError(
            "Fajl je prevelik. Maksimalna veličina je 10MB.",
            details={"code": "FILE_TOO_LARGE"},
        )

    resolved_subject_id: str | None = None
    if visibility is DocumentVisibility.SUBJECT:
        if not subject_person_id:
            raise BadRequestError(
                "Potrebno je navesti osobu na koju se dokument odnosi.",
                details={"code": "SUBJECT_REQUIRED"},
            )
        if not repository.is_school_member(db, context.school_id, subject_person_id):
            raise BadRequestError(
                "Navedena osoba nije član ove organizacije.",
                details={"code": "SUBJECT_NOT_A_MEMBER"},
            )
        resolved_subject_id = subject_person_id

    storage_key = _storage().save(data)
    document = Document(
        school_id=context.school_id,
        owner_person_id=context.person_id,
        subject_person_id=resolved_subject_id,
        filename=filename[:255] or "dokument",
        content_type=content_type,
        size_bytes=len(data),
        storage_key=storage_key,
        document_type=document_type,
        visibility=visibility,
        retention_period=retention_period,
    )
    db.add(document)
    db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.DOCUMENT,
        action="document.uploaded",
        entity_type="document",
        entity_id=document.id,
        summary=f"Otpremljen dokument: {document.filename}",
        school_id=context.school_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="document.uploaded",
        payload={"document_id": document.id, "school_id": context.school_id},
        school_id=context.school_id,
    )
    db.commit()
    return _to_response(document)


def list_documents(
    db: Session,
    context: RequestContext,
    params: PageParams,
    *,
    document_type: DocumentType | None = None,
    subject_person_id: str | None = None,
) -> Page[DocumentResponse]:
    if _has_documents_permission(context):
        documents, total = repository.list_school_documents(
            db,
            context.school_id,
            params,
            document_type=document_type,
            subject_person_id=subject_person_id,
        )
    else:
        visible_ids = repository.guardian_child_ids(
            db, context.school_id, context.person_id
        )
        documents, total = repository.list_visible_documents(
            db, context.school_id, context.person_id, visible_ids, params
        )
    items = [_to_response(d) for d in documents]
    return Page.build(items, total, params)


def get_document_metadata(
    db: Session, context: RequestContext, document_id: str
) -> DocumentResponse:
    document = _load_authorized(db, context, document_id)
    return _to_response(document)


def download_document(
    db: Session, context: RequestContext, document_id: str
) -> DocumentContent:
    document = _load_authorized(db, context, document_id)
    try:
        data = _storage().load(document.storage_key)
    except FileNotFoundError as exc:
        # The metadata row exists but its bytes don't, a storage-layer problem,
        # not a caller error. Never expose the filesystem path.
        raise NotFoundError("Sadržaj dokumenta trenutno nije dostupan.") from exc
    return DocumentContent(
        filename=document.filename, content_type=document.content_type, data=data
    )


def acknowledge_document(
    db: Session, context: RequestContext, document_id: str
) -> DocumentResponse:
    """The subject themselves, or a guardian acting for that subject, records an
    acknowledgement of a CONTRACT document. Deliberately narrower than
    ``_can_view``: staff can see a SUBJECT document to administer it, but
    acknowledging is the subject's (or their guardian's) act, not staff's."""
    document = _load_authorized(db, context, document_id)
    if document.document_type is not DocumentType.CONTRACT:
        raise BadRequestError(
            "Samo dokumenti tipa ugovor zahtevaju potvrdu.",
            details={"code": "NOT_A_CONTRACT"},
        )

    is_subject = document.subject_person_id == context.person_id
    is_guardian = document.subject_person_id is not None and (
        document.subject_person_id
        in repository.guardian_child_ids(db, context.school_id, context.person_id)
    )
    if not (is_subject or is_guardian):
        raise ForbiddenError(
            "Samo osoba na koju se ugovor odnosi, ili njen staratelj, može da ga potvrdi."
        )

    if document.acknowledged_at is None:
        document.acknowledged_at = _now()
        document.acknowledged_by_person_id = context.person_id
        record_audit(
            db,
            data_class=AuditDataClass.DOCUMENT,
            action="document.acknowledged",
            entity_type="document",
            entity_id=document.id,
            summary="Potvrđen ugovor.",
            school_id=context.school_id,
            actor_person_id=context.person_id,
        )
        db.commit()
    return _to_response(document)
