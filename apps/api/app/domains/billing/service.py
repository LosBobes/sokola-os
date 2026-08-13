from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.config import get_settings
from app.domains.billing import repository
from app.domains.billing.enums import ChargeSourceType, ChargeStatus
from app.domains.billing.models import BillingRun, Charge
from app.domains.billing.schemas import (
    BillingPreviewItem,
    BillingPreviewRequest,
    BillingPreviewResponse,
    BillingRunResponse,
    CancelChargeRequest,
    ChargeResponse,
    DebtSummaryResponse,
    PersonDebtItem,
    PostBillingRunRequest,
)
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def _compute(
    db: Session, context: RequestContext, req: BillingPreviewRequest
) -> tuple[list[BillingPreviewItem], int, str, str]:
    """PRD 07 M1: with an explicit ``amount_minor`` it's charged to every member
    unchanged (caller override, e.g. a one-off fee). Omitted, the amount is
    derived per member from the group's pricing: ``Group.base_monthly_price_
    minor`` minus that member's ``GroupMembership.discount_minor``, floored at
    0 so a discount can never make a charge negative."""
    group = repository.get_org_group(db, context.organization_id, req.group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")
    currency = get_settings().default_currency

    if req.amount_minor is not None:
        people = repository.active_group_people(db, req.group_id)
        items = [
            BillingPreviewItem(
                person_id=p.id, display_name=p.display_name, amount_minor=req.amount_minor
            )
            for p in people
        ]
    else:
        if group.base_monthly_price_minor is None:
            raise ConflictError(
                "Grupa nema podešenu cenu; unesite iznos ili podesite cenu grupe.",
                details={"code": "GROUP_PRICE_NOT_SET"},
            )
        base_price = group.base_monthly_price_minor
        members = repository.active_group_members_with_discount(db, req.group_id)
        items = [
            BillingPreviewItem(
                person_id=p.id,
                display_name=p.display_name,
                amount_minor=max(base_price - discount, 0),
            )
            for p, discount in members
        ]

    total = sum(i.amount_minor for i in items)
    # The fingerprint covers each member's resolved amount (not just the
    # request), so a roster change OR a pricing/discount change between
    # preview and post both invalidate the hash and force a fresh review.
    fingerprint = {
        "group_id": req.group_id,
        "description": req.description,
        "period_label": req.period_label,
        "currency": currency,
        "items": [{"person_id": i.person_id, "amount_minor": i.amount_minor} for i in items],
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
    since the preview, the recomputed hash won't match and posting is refused , 
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
            "Obračun je zastareo. Spisak članova se promenio, pregledajte ponovo.",
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


def cancel_charge(
    db: Session,
    context: RequestContext,
    charge_id: str,
    req: CancelChargeRequest,
    idempotency_key: str | None,
) -> ChargeResponse:
    """PRD 07 P1. A charge is only cancellable while it hasn't been settled
    (PAID) or already cancelled, a partially-paid charge can still be
    cancelled (e.g. waiving the remainder); voiding the payments already
    applied to it is a separate operation (PRD 07 P2)."""
    params = {"charge_id": charge_id, **req.model_dump()}
    guard = None
    if idempotency_key:
        guard = idempotency.begin(
            db, context.organization_id, "billing.cancel_charge", idempotency_key, params
        )
        if guard.replay is not None:
            return ChargeResponse.model_validate(guard.replay["body"])

    charge = repository.get_charge_for_update(db, context.organization_id, charge_id)
    if charge is None:
        raise NotFoundError("Zaduženje nije pronađeno.")
    if charge.status in (ChargeStatus.PAID, ChargeStatus.CANCELLED):
        raise ConflictError(
            "Zaduženje se ne može otkazati u ovom stanju.",
            details={"code": "CHARGE_NOT_CANCELLABLE", "status": charge.status.value},
        )

    charge.status = ChargeStatus.CANCELLED
    charge.cancellation_reason = req.reason
    if req.note:
        charge.note = req.note
    db.flush()

    result = ChargeResponse.model_validate(charge)
    record_audit(
        db,
        data_class=AuditDataClass.FINANCIAL,
        action="charge.cancelled",
        entity_type="charge",
        entity_id=charge.id,
        summary=f"Otkazano zaduženje ({req.reason.value}).",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="charge.cancelled",
        payload={"charge_id": charge.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    if guard is not None:
        idempotency.complete(db, guard, status=200, body=result.model_dump(mode="json"))
    db.commit()
    return result


def list_debts(
    db: Session, context: RequestContext, params: PageParams
) -> Page[PersonDebtItem]:
    """PRD 07 M2. Per-person outstanding balance across OPEN/PARTIALLY_PAID
    charges, worst debtor first."""
    rows, total = repository.person_debts(db, context.organization_id, params)
    items = [
        PersonDebtItem(
            person_id=person_id,
            display_name=display_name,
            currency=currency,
            outstanding_minor=outstanding_minor,
            open_charge_count=open_charge_count,
        )
        for person_id, display_name, currency, outstanding_minor, open_charge_count in rows
    ]
    return Page.build(items, total, params)


def debt_summary(db: Session, context: RequestContext) -> DebtSummaryResponse:
    """PRD 07 M2. Org-wide roll-up of :func:`list_debts`."""
    total_minor, people = repository.debt_summary(db, context.organization_id)
    return DebtSummaryResponse(
        currency=get_settings().default_currency,
        total_outstanding_minor=total_minor,
        people_with_debt=people,
    )
