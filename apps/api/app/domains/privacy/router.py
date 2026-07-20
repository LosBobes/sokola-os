from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.common.pagination import Page, PageParams, page_params
from app.domains.privacy import service
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
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["privacy"])

# All privacy endpoints are staff-facing (consent/DSAR/retention administration)
# and gated on the PRIVACY area.
_privacy_staff = require_permission(PermissionArea.PRIVACY)
PrivacyContext = Annotated[ContextDep, Depends(_privacy_staff)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


@router.post(
    "/consents",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="recordConsent",
)
def record_consent(
    body: RecordConsentRequest, db: DbDep, context: PrivacyContext
) -> ConsentResponse:
    return service.record_consent(db, context, body)


@router.get("/consents", response_model=Page[ConsentResponse], operation_id="listConsents")
def list_consents(
    person_id: Annotated[str, Query()],
    db: DbDep,
    context: PrivacyContext,
    params: PageParamsDep,
) -> Page[ConsentResponse]:
    return service.list_person_consents(db, context, person_id, params)


@router.post(
    "/consents/{consent_id}/withdraw",
    response_model=ConsentResponse,
    operation_id="withdrawConsent",
    responses={409: {"description": "Consent already withdrawn."}},
)
def withdraw_consent(
    consent_id: str, body: WithdrawConsentRequest, db: DbDep, context: PrivacyContext
) -> ConsentResponse:
    return service.withdraw_consent(db, context, consent_id, body)


# ---------------------------------------------------------------------------
# Data-subject requests (DSAR)
# ---------------------------------------------------------------------------


@router.post(
    "/dsar-requests",
    response_model=DsarRequestResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createDsarRequest",
)
def create_dsar_request(
    body: CreateDsarRequest, db: DbDep, context: PrivacyContext
) -> DsarRequestResponse:
    return service.create_dsar_request(db, context, body)


@router.get(
    "/dsar-requests", response_model=Page[DsarRequestResponse], operation_id="listDsarRequests"
)
def list_dsar_requests(
    db: DbDep,
    context: PrivacyContext,
    params: PageParamsDep,
    person_id: Annotated[str | None, Query()] = None,
) -> Page[DsarRequestResponse]:
    return service.list_dsar_requests(db, context, params, person_id=person_id)


@router.get(
    "/dsar-requests/{request_id}",
    response_model=DsarRequestResponse,
    operation_id="getDsarRequest",
)
def get_dsar_request(request_id: str, db: DbDep, context: PrivacyContext) -> DsarRequestResponse:
    return service.get_dsar_request(db, context, request_id)


@router.post(
    "/dsar-requests/{request_id}/start",
    response_model=DsarRequestResponse,
    operation_id="startDsarRequest",
    responses={409: {"description": "Only a PENDING request may be started."}},
)
def start_dsar_request(
    request_id: str, db: DbDep, context: PrivacyContext
) -> DsarRequestResponse:
    return service.start_dsar_request(db, context, request_id)


@router.post(
    "/dsar-requests/{request_id}/fulfill",
    response_model=DsarRequestResponse,
    operation_id="fulfillDsarRequest",
    responses={409: {"description": "Request already decided."}},
)
def fulfill_dsar_request(
    request_id: str, body: DecideDsarRequest, db: DbDep, context: PrivacyContext
) -> DsarRequestResponse:
    return service.fulfill_dsar_request(db, context, request_id, body)


@router.post(
    "/dsar-requests/{request_id}/reject",
    response_model=DsarRequestResponse,
    operation_id="rejectDsarRequest",
    responses={409: {"description": "Request already decided."}},
)
def reject_dsar_request(
    request_id: str, body: DecideDsarRequest, db: DbDep, context: PrivacyContext
) -> DsarRequestResponse:
    return service.reject_dsar_request(db, context, request_id, body)


# ---------------------------------------------------------------------------
# Retention periods
# ---------------------------------------------------------------------------


@router.post(
    "/retention-periods",
    response_model=RetentionPeriodResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createRetentionPeriod",
    responses={
        409: {"description": "An active retention period already exists for this category."}
    },
)
def create_retention_period(
    body: CreateRetentionPeriodRequest, db: DbDep, context: PrivacyContext
) -> RetentionPeriodResponse:
    return service.create_retention_period(db, context, body)


@router.get(
    "/retention-periods",
    response_model=Page[RetentionPeriodResponse],
    operation_id="listRetentionPeriods",
)
def list_retention_periods(
    db: DbDep, context: PrivacyContext, params: PageParamsDep
) -> Page[RetentionPeriodResponse]:
    return service.list_retention_periods(db, context, params)


@router.get(
    "/retention-periods/{retention_period_id}",
    response_model=RetentionPeriodResponse,
    operation_id="getRetentionPeriod",
)
def get_retention_period(
    retention_period_id: str, db: DbDep, context: PrivacyContext
) -> RetentionPeriodResponse:
    return service.get_retention_period(db, context, retention_period_id)


@router.patch(
    "/retention-periods/{retention_period_id}",
    response_model=RetentionPeriodResponse,
    operation_id="updateRetentionPeriod",
)
def update_retention_period(
    retention_period_id: str,
    body: UpdateRetentionPeriodRequest,
    db: DbDep,
    context: PrivacyContext,
) -> RetentionPeriodResponse:
    return service.update_retention_period(db, context, retention_period_id, body)


@router.post(
    "/retention-periods/{retention_period_id}/deactivate",
    response_model=RetentionPeriodResponse,
    operation_id="deactivateRetentionPeriod",
)
def deactivate_retention_period(
    retention_period_id: str, db: DbDep, context: PrivacyContext
) -> RetentionPeriodResponse:
    return service.deactivate_retention_period(db, context, retention_period_id)
