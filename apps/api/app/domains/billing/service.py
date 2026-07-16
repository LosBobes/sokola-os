from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.common.context import RequestContext
from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.config import get_settings
from app.domains.billing import repository
from app.domains.billing.enums import ChargeSourceType
from app.domains.billing.models import BillingRun, Charge
from app.domains.billing.schemas import (
    BillingPreviewItem,
    BillingPreviewRequest,
    BillingPreviewResponse,
    BillingRunResponse,
    ChargeResponse,
    PostBillingRunRequest,
)
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue


def _compute(
    db: Session, context: RequestContext, req: BillingPreviewRequest
) -> tuple[list[BillingPreviewItem], int, str, str]:
    if repository.get_org_group(db, context.organization_id, req.group_id) is None:
        raise NotFoundError("Grupa nije pronađena.")
    currency = get_settings().default_currency
    people = repository.active_group_people(db, req.group_id)
    items = [
        BillingPreviewItem(
            person_id=p.id, display_name=p.display_name, amount_minor=req.amount_minor
        )
        for p in people
    ]
    total = sum(i.amount_minor for i in items)
    fingerprint = {
        "group_id": req.group_id,
        "amount_minor": req.amount_minor,
        "description": req.description,
        "period_label": req.period_label,
        "currency": currency,
        "people": [i.person_id for i in items],
    }
    canonical = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
    preview_hash = hashlib.sha256(canonical.encode()).hexdigest()
    return items, total, currency, preview_hash


def preview(
    db: Session, context: RequestContext, req: BillingPreviewRequest
) -> BillingPreviewResponse:
    items, total, currency, preview_hash = _compute(db, context, req)
    return BillingPreviewResponse(
        preview_hash=preview_hash, currency=currency, total_minor=total, items=items
    )


def post_run(
    db: Session,
    context: RequestContext,
    req: PostBillingRunRequest,
    idempotency_key: str | None,
) -> BillingRunResponse:
    """Journey 5. Post charges from the reviewed preview. If the roster changed
    since the preview, the recomputed hash won't match and posting is refused —
    the manager must review the new preview."""
    params = req.model_dump()
    guard = None
    if idempotency_key:
        guard = idempotency.begin(
            db, context.organization_id, "billing.post_run", idempotency_key, params
        )
        if guard.replay is not None:
            return BillingRunResponse.model_validate(guard.replay["body"])

    items, total, currency, current_hash = _compute(db, context, req)
    if current_hash != req.preview_hash:
        raise ConflictError(
            "Obračun je zastareo — spisak članova se promenio. Pregledajte ponovo.",
            details={"code": "PREVIEW_STALE"},
        )
    if not items:
        raise ConflictError("Nema članova za obračun u ovoj grupi.")

    run = BillingRun(
        organization_id=context.organization_id,
        description=req.description,
        period_label=req.period_label,
        currency=currency,
        total_minor=total,
        charge_count=len(items),
    )
    db.add(run)
    db.flush()
    for item in items:
        db.add(
            Charge(
                organization_id=context.organization_id,
                person_id=item.person_id,
                billing_run_id=run.id,
                source_type=ChargeSourceType.MEMBERSHIP,
                description=req.description,
                currency=currency,
                amount_due_minor=item.amount_minor,
            )
        )

    result = BillingRunResponse.model_validate(run)
    record_audit(
        db,
        data_class=AuditDataClass.FINANCIAL,
        action="billing_run.posted",
        entity_type="billing_run",
        entity_id=run.id,
        summary=f"Proknjižen obračun „{req.description}“ ({len(items)} zaduženja).",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="billing_run.posted",
        payload={"billing_run_id": run.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    if guard is not None:
        idempotency.complete(db, guard, status=201, body=result.model_dump(mode="json"))
    db.commit()
    return result


def list_charges(
    db: Session, context: RequestContext, params: PageParams, person_id: str | None
) -> Page[ChargeResponse]:
    charges, total = repository.list_charges(db, context.organization_id, params, person_id)
    return Page.build([ChargeResponse.model_validate(c) for c in charges], total, params)
