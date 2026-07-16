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
    ChargeResponse,
    PostBillingRunRequest,
)
from app.domains.identity.enums import RoleCode
from app.security.deps import ContextDep, DbDep, require_roles

router = APIRouter(tags=["billing"])

_finance = require_roles(RoleCode.OWNER, RoleCode.MANAGER, RoleCode.ADMIN)
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
