from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.identity.models import Person
from app.domains.organization.models import OrganizationMembership
from app.domains.privacy.enums import DataCategory
from app.domains.privacy.models import ConsentRecord, DataSubjectRequest, RetentionPeriod


def get_org_person(db: Session, organization_id: str, person_id: str) -> Person | None:
    """A person visible through an active membership in this org — the same
    visibility rule every domain applies before touching someone's data."""
    stmt = (
        select(Person)
        .join(OrganizationMembership, OrganizationMembership.person_id == Person.id)
        .where(
            Person.id == person_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


def get_org_consent(db: Session, organization_id: str, consent_id: str) -> ConsentRecord | None:
    stmt = select(ConsentRecord).where(
        ConsentRecord.id == consent_id, ConsentRecord.organization_id == organization_id
    )
    return db.execute(stmt).scalar_one_or_none()


def list_person_consents(
    db: Session, organization_id: str, person_id: str, params: PageParams
) -> tuple[list[ConsentRecord], int]:
    base = select(ConsentRecord).where(
        ConsentRecord.organization_id == organization_id,
        ConsentRecord.person_id == person_id,
    )
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(ConsentRecord.granted_at.desc())
            .limit(params.limit)
            .offset(params.offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


# ---------------------------------------------------------------------------
# DSAR
# ---------------------------------------------------------------------------


def get_org_dsar_request(
    db: Session, organization_id: str, request_id: str
) -> DataSubjectRequest | None:
    stmt = select(DataSubjectRequest).where(
        DataSubjectRequest.id == request_id,
        DataSubjectRequest.organization_id == organization_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_org_dsar_requests(
    db: Session, organization_id: str, params: PageParams, *, person_id: str | None = None
) -> tuple[list[DataSubjectRequest], int]:
    base = select(DataSubjectRequest).where(DataSubjectRequest.organization_id == organization_id)
    if person_id is not None:
        base = base.where(DataSubjectRequest.person_id == person_id)
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(DataSubjectRequest.created_at.desc())
            .limit(params.limit)
            .offset(params.offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


# ---------------------------------------------------------------------------
# Retention periods
# ---------------------------------------------------------------------------


def get_org_retention_period(
    db: Session, organization_id: str, retention_period_id: str
) -> RetentionPeriod | None:
    stmt = select(RetentionPeriod).where(
        RetentionPeriod.id == retention_period_id,
        RetentionPeriod.organization_id == organization_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_org_retention_periods(
    db: Session, organization_id: str, params: PageParams
) -> tuple[list[RetentionPeriod], int]:
    base = select(RetentionPeriod).where(
        RetentionPeriod.organization_id == organization_id,
        RetentionPeriod.record_status == RecordStatus.ACTIVE,
    )
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(RetentionPeriod.data_category).limit(params.limit).offset(params.offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def retention_period_category_taken(
    db: Session,
    organization_id: str,
    data_category: DataCategory,
    *,
    exclude_id: str | None = None,
) -> bool:
    stmt = select(RetentionPeriod.id).where(
        RetentionPeriod.organization_id == organization_id,
        RetentionPeriod.data_category == data_category,
        RetentionPeriod.record_status == RecordStatus.ACTIVE,
    )
    if exclude_id is not None:
        stmt = stmt.where(RetentionPeriod.id != exclude_id)
    return db.execute(stmt.limit(1)).first() is not None


__all__ = [
    "get_org_consent",
    "get_org_dsar_request",
    "get_org_person",
    "get_org_retention_period",
    "list_org_dsar_requests",
    "list_org_retention_periods",
    "list_person_consents",
    "retention_period_category_taken",
]
