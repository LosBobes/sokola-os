"""Privacy domain (PRD 12): consent records, data-subject requests (DSAR),
and per-category retention periods.

Scope cuts, deliberate (see PR description):
* DSAR fulfilment is a manual staff attestation (a note), not an automated
  data export/erasure — that is a larger, separate effort.
* Retention periods are a data model only; no automated expiry/purge job
  reads them yet.
* The consent-gating hook (``consent_gate.has_active_consent``) is not wired
  into any other domain — each domain adopts it as its own follow-up.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.domains.privacy import repository
from app.domains.privacy.enums import DsarRequestStatus
from app.domains.privacy.models import ConsentRecord, DataSubjectRequest, RetentionPeriod
from app.domains.privacy.schemas import (
    ConsentResponse,
    CreateDsarRequest,
    CreateRetentionPeriodRequest,
    DecideDsarRequest,
    DsarRequestResponse,
    RecordConsentRequest,
    RetentionPeriodResponse,
    UpdateRetentionPeriodRequest,
    WithdrawConsentRequest,
)
from app.platform.audit.service import record_audit
from app.security.context import RequestContext

_PERSON_NOT_FOUND = "Osoba nije pronađena u ovoj školi."
_RETENTION_CATEGORY_CONFLICT = "Rok čuvanja za ovu kategoriju podataka već postoji."


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _require_org_person(db: Session, context: RequestContext, person_id: str) -> None:
    if repository.get_org_person(db, context.organization_id, person_id) is None:
        raise NotFoundError(_PERSON_NOT_FOUND)


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


def _consent_response(row: ConsentRecord) -> ConsentResponse:
    return ConsentResponse(
        id=row.id,
        person_id=row.person_id,
        scope=row.scope,
        granted_at=row.granted_at,
        revoked_at=row.revoked_at,
        note=row.note,
    )


def record_consent(
    db: Session, context: RequestContext, req: RecordConsentRequest
) -> ConsentResponse:
    _require_org_person(db, context, req.person_id)
    consent = ConsentRecord(
        organization_id=context.organization_id,
        person_id=req.person_id,
        scope=req.scope,
        granted_at=_now(),
        note=req.note.strip() if req.note else None,
        recorded_by_person_id=context.person_id,
    )
    db.add(consent)
    db.flush()
    record_audit(
        db,
        data_class=AuditDataClass.DATA_REQUEST,
        action="privacy.consent.recorded",
        entity_type="privacy_consent_record",
        entity_id=consent.id,
        summary=f"Saglasnost evidentirana za svrhu {req.scope.value}.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"person_id": req.person_id, "scope": req.scope.value},
    )
    db.commit()
    return _consent_response(consent)


def list_person_consents(
    db: Session, context: RequestContext, person_id: str, params: PageParams
) -> Page[ConsentResponse]:
    _require_org_person(db, context, person_id)
    rows, total = repository.list_person_consents(db, context.organization_id, person_id, params)
    return Page.build([_consent_response(r) for r in rows], total, params)


def withdraw_consent(
    db: Session, context: RequestContext, consent_id: str, req: WithdrawConsentRequest
) -> ConsentResponse:
    row = repository.get_org_consent(db, context.organization_id, consent_id)
    if row is None:
        raise NotFoundError("Saglasnost nije pronađena.")
    if row.revoked_at is not None:
        raise ConflictError("Saglasnost je već povučena.")
    row.revoked_at = _now()
    if req.note and req.note.strip():
        row.note = f"{row.note}\n{req.note.strip()}" if row.note else req.note.strip()
    record_audit(
        db,
        data_class=AuditDataClass.DATA_REQUEST,
        action="privacy.consent.withdrawn",
        entity_type="privacy_consent_record",
        entity_id=row.id,
        summary=f"Saglasnost povučena za svrhu {row.scope.value}.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"person_id": row.person_id, "scope": row.scope.value},
    )
    db.commit()
    return _consent_response(row)


# ---------------------------------------------------------------------------
# Data-subject requests (DSAR)
# ---------------------------------------------------------------------------


def _dsar_response(row: DataSubjectRequest) -> DsarRequestResponse:
    return DsarRequestResponse(
        id=row.id,
        person_id=row.person_id,
        request_type=row.request_type,
        status=row.status,
        note=row.note,
        decision_note=row.decision_note,
        decided_at=row.decided_at,
        created_at=row.created_at,
    )


def create_dsar_request(
    db: Session, context: RequestContext, req: CreateDsarRequest
) -> DsarRequestResponse:
    _require_org_person(db, context, req.person_id)
    request = DataSubjectRequest(
        organization_id=context.organization_id,
        person_id=req.person_id,
        request_type=req.request_type,
        status=DsarRequestStatus.PENDING,
        note=req.note.strip() if req.note else None,
        requested_by_person_id=context.person_id,
    )
    db.add(request)
    db.flush()
    record_audit(
        db,
        data_class=AuditDataClass.DATA_REQUEST,
        action="privacy.dsar.requested",
        entity_type="privacy_data_subject_request",
        entity_id=request.id,
        summary=f"Zahtev tipa {req.request_type.value} zaveden za osobu.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"person_id": req.person_id, "request_type": req.request_type.value},
    )
    db.commit()
    return _dsar_response(request)


def list_dsar_requests(
    db: Session, context: RequestContext, params: PageParams, *, person_id: str | None = None
) -> Page[DsarRequestResponse]:
    if person_id is not None:
        _require_org_person(db, context, person_id)
    rows, total = repository.list_org_dsar_requests(
        db, context.organization_id, params, person_id=person_id
    )
    return Page.build([_dsar_response(r) for r in rows], total, params)


def get_dsar_request(db: Session, context: RequestContext, request_id: str) -> DsarRequestResponse:
    row = repository.get_org_dsar_request(db, context.organization_id, request_id)
    if row is None:
        raise NotFoundError("Zahtev nije pronađen.")
    return _dsar_response(row)


def start_dsar_request(
    db: Session, context: RequestContext, request_id: str
) -> DsarRequestResponse:
    row = repository.get_org_dsar_request(db, context.organization_id, request_id)
    if row is None:
        raise NotFoundError("Zahtev nije pronađen.")
    if row.status is not DsarRequestStatus.PENDING:
        raise ConflictError("Samo zahtev na čekanju može preći u obradu.")
    row.status = DsarRequestStatus.IN_PROGRESS
    record_audit(
        db,
        data_class=AuditDataClass.DATA_REQUEST,
        action="privacy.dsar.started",
        entity_type="privacy_data_subject_request",
        entity_id=row.id,
        summary="Zahtev je preuzet u obradu.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    db.commit()
    return _dsar_response(row)


def _decide_dsar_request(
    db: Session,
    context: RequestContext,
    request_id: str,
    req: DecideDsarRequest,
    *,
    outcome: DsarRequestStatus,
    action: str,
    summary: str,
) -> DsarRequestResponse:
    row = repository.get_org_dsar_request(db, context.organization_id, request_id)
    if row is None:
        raise NotFoundError("Zahtev nije pronađen.")
    if row.status not in (DsarRequestStatus.PENDING, DsarRequestStatus.IN_PROGRESS):
        raise ConflictError("Zahtev je već rešen.")
    row.status = outcome
    row.decision_note = req.note.strip()
    row.decided_by_person_id = context.person_id
    row.decided_at = _now()
    record_audit(
        db,
        data_class=AuditDataClass.DATA_REQUEST,
        action=action,
        entity_type="privacy_data_subject_request",
        entity_id=row.id,
        summary=summary,
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"decision_note": row.decision_note},
    )
    db.commit()
    return _dsar_response(row)


def fulfill_dsar_request(
    db: Session, context: RequestContext, request_id: str, req: DecideDsarRequest
) -> DsarRequestResponse:
    """v1 fulfilment is a manual staff attestation: no automated data export
    or erasure runs off this — see the PR description's scope cuts."""
    return _decide_dsar_request(
        db,
        context,
        request_id,
        req,
        outcome=DsarRequestStatus.FULFILLED,
        action="privacy.dsar.fulfilled",
        summary="Zahtev je označen kao ispunjen.",
    )


def reject_dsar_request(
    db: Session, context: RequestContext, request_id: str, req: DecideDsarRequest
) -> DsarRequestResponse:
    return _decide_dsar_request(
        db,
        context,
        request_id,
        req,
        outcome=DsarRequestStatus.REJECTED,
        action="privacy.dsar.rejected",
        summary="Zahtev je odbijen.",
    )


# ---------------------------------------------------------------------------
# Retention periods
# ---------------------------------------------------------------------------


def _retention_response(row: RetentionPeriod) -> RetentionPeriodResponse:
    return RetentionPeriodResponse(
        id=row.id,
        data_category=row.data_category,
        retention_period_days=row.retention_period_days,
        note=row.note,
        status=row.record_status,
    )


def create_retention_period(
    db: Session, context: RequestContext, req: CreateRetentionPeriodRequest
) -> RetentionPeriodResponse:
    if repository.retention_period_category_taken(db, context.organization_id, req.data_category):
        raise ConflictError(_RETENTION_CATEGORY_CONFLICT)
    row = RetentionPeriod(
        organization_id=context.organization_id,
        data_category=req.data_category,
        retention_period_days=req.retention_period_days,
        note=req.note.strip() if req.note else None,
    )
    db.add(row)
    db.commit()
    return _retention_response(row)


def list_retention_periods(
    db: Session, context: RequestContext, params: PageParams
) -> Page[RetentionPeriodResponse]:
    rows, total = repository.list_org_retention_periods(db, context.organization_id, params)
    return Page.build([_retention_response(r) for r in rows], total, params)


def get_retention_period(
    db: Session, context: RequestContext, retention_period_id: str
) -> RetentionPeriodResponse:
    row = repository.get_org_retention_period(db, context.organization_id, retention_period_id)
    if row is None:
        raise NotFoundError("Rok čuvanja nije pronađen.")
    return _retention_response(row)


def update_retention_period(
    db: Session,
    context: RequestContext,
    retention_period_id: str,
    req: UpdateRetentionPeriodRequest,
) -> RetentionPeriodResponse:
    row = repository.get_org_retention_period(db, context.organization_id, retention_period_id)
    if row is None:
        raise NotFoundError("Rok čuvanja nije pronađen.")
    if "retention_period_days" in req.model_fields_set and req.retention_period_days is not None:
        row.retention_period_days = req.retention_period_days
    if "note" in req.model_fields_set:
        row.note = req.note.strip() if req.note else None
    db.commit()
    return _retention_response(row)


def deactivate_retention_period(
    db: Session, context: RequestContext, retention_period_id: str
) -> RetentionPeriodResponse:
    row = repository.get_org_retention_period(db, context.organization_id, retention_period_id)
    if row is None:
        raise NotFoundError("Rok čuvanja nije pronađen.")
    row.record_status = RecordStatus.ARCHIVED
    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="privacy.retention_period.deactivated",
        entity_type="privacy_retention_period",
        entity_id=row.id,
        summary=f"Rok čuvanja za {row.data_category.value} je deaktiviran.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    db.commit()
    return _retention_response(row)
