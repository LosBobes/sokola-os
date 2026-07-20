from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.common.http import IdempotencyKey
from app.common.pagination import Page, PageParams, page_params
from app.domains.billing import service
from app.domains.billing.schemas import (
    BillingPreviewRequest,
    BillingPreviewResponse,
    BillingRunResponse,
    CancelChargeRequest,
    ChargeResponse,
    DebtSummaryResponse,
    PersonDebtItem,
    PostBillingRunRequest,
)
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["billing"])

_finance = require_permission(PermissionArea.BILLING)
FinanceContext = Annotated[ContextDep, Depends(_finance)]


@router.post(
    "/billing/runs/preview",
    response_model=BillingPreviewResponse,
    operation_id="previewBillingRun",
)
def preview_billing_run(
    body: BillingPreviewRequest, db: DbDep, context: FinanceContext
) -> BillingPreviewResponse:
    return service.preview(db, context, body)


@router.post(
    "/billing/runs",
    response_model=BillingRunResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="postBillingRun",
    responses={409: {"description": "Preview is stale; review again."}},
)
def post_billing_run(
    body: PostBillingRunRequest,
    db: DbDep,
    context: FinanceContext,
    idempotency_key: IdempotencyKey = None,
) -> BillingRunResponse:
    return service.post_run(db, context, body, idempotency_key)


@router.get("/charges", response_model=Page[ChargeResponse], operation_id="listCharges")
def list_charges(
    db: DbDep,
    context: ContextDep,
    params: Annotated[PageParams, Depends(page_params)],
    person_id: Annotated[str | None, Query()] = None,
) -> Page[ChargeResponse]:
    return service.list_charges(db, context, params, person_id)


@router.post(
    "/charges/{charge_id}/cancel",
    response_model=ChargeResponse,
    operation_id="cancelCharge",
    responses={409: {"description": "Charge already PAID or already CANCELLED."}},
)
def cancel_charge(
    charge_id: str,
    body: CancelChargeRequest,
    db: DbDep,
    context: FinanceContext,
    idempotency_key: IdempotencyKey = None,
) -> ChargeResponse:
    return service.cancel_charge(db, context, charge_id, body, idempotency_key)


@router.get(
    "/billing/debts",
    response_model=Page[PersonDebtItem],
    operation_id="listDebts",
)
def list_debts(
    db: DbDep,
    context: ContextDep,
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[PersonDebtItem]:
    return service.list_debts(db, context, params)


@router.get(
    "/billing/debts/summary",
    response_model=DebtSummaryResponse,
    operation_id="getDebtSummary",
)
def get_debt_summary(db: DbDep, context: ContextDep) -> DebtSummaryResponse:
    return service.debt_summary(db, context)
