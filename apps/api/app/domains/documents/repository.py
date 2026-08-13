from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.documents.enums import DocumentType, DocumentVisibility
from app.domains.documents.models import Document
from app.domains.organization.models import OrganizationMembership
from app.domains.people.enums import GuardianAccessStatus
from app.domains.people.models import GuardianOrganizationAccess


def get_document(db: Session, organization_id: str, document_id: str) -> Document | None:
    """Org-scoped lookup, filtering by ``organization_id`` in the query itself
    means a cross-tenant id simply doesn't match, so callers get a clean 404
    without ever branching on "wrong org" vs "no such id" (never confirm
    existence of a document the caller's tenant doesn't own)."""
    stmt = select(Document).where(
        Document.id == document_id,
        Document.organization_id == organization_id,
        Document.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def is_org_member(db: Session, organization_id: str, person_id: str) -> bool:
    stmt = select(OrganizationMembership.id).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.person_id == person_id,
        OrganizationMembership.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None


def guardian_child_ids(db: Session, organization_id: str, guardian_person_id: str) -> set[str]:
    """The children this guardian may act for in THIS organization, the same
    relationship the events domain resolves guardian access through."""
    stmt = select(GuardianOrganizationAccess.child_person_id).where(
        GuardianOrganizationAccess.organization_id == organization_id,
        GuardianOrganizationAccess.guardian_person_id == guardian_person_id,
        GuardianOrganizationAccess.status == GuardianAccessStatus.ACTIVE,
    )
    return set(db.execute(stmt).scalars().all())


def list_org_documents(
    db: Session,
    organization_id: str,
    params: PageParams,
    *,
    document_type: DocumentType | None = None,
    subject_person_id: str | None = None,
) -> tuple[list[Document], int]:
    """Staff view: every active document in the tenant, optionally filtered."""
    filters = [
        Document.organization_id == organization_id,
        Document.record_status == RecordStatus.ACTIVE,
    ]
    if document_type is not None:
        filters.append(Document.document_type == document_type)
    if subject_person_id is not None:
        filters.append(Document.subject_person_id == subject_person_id)

    total = db.execute(
        select(func.count()).select_from(Document).where(*filters)
    ).scalar_one()
    stmt = (
        select(Document)
        .where(*filters)
        .order_by(Document.created_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    )
    return list(db.execute(stmt).scalars().all()), total


def list_visible_documents(
    db: Session,
    organization_id: str,
    viewer_person_id: str,
    visible_subject_ids: set[str],
    params: PageParams,
) -> tuple[list[Document], int]:
    """Non-staff view: only SUBJECT-visibility documents about a subject the
    caller may view (themselves, or a child they guardian)."""
    subject_ids = visible_subject_ids | {viewer_person_id}
    filters = [
        Document.organization_id == organization_id,
        Document.record_status == RecordStatus.ACTIVE,
        Document.visibility == DocumentVisibility.SUBJECT,
        Document.subject_person_id.in_(subject_ids),
    ]

    total = db.execute(
        select(func.count()).select_from(Document).where(*filters)
    ).scalar_one()
    stmt = (
        select(Document)
        .where(*filters)
        .order_by(Document.created_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    )
    return list(db.execute(stmt).scalars().all()), total
