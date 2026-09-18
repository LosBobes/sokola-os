from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common import money
from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, NotFoundError
from app.common.ids import new_id
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
    PaymentSlipResponse,
    PersonDebtItem,
    PostBillingRunRequest,
)
from app.domains.payments import ips_qr
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext
from app.security.permissions import (
    PermissionArea,
    effective_areas,
    parse_granted_areas,
)


def _compute(
    db: Session, context: RequestContext, req: BillingPreviewRequest
) -> tuple[list[BillingPreviewItem], Decimal, str, str]:
    """PRD 07 M1: with an explicit ``amount`` it's charged to every member
    unchanged (caller override, e.g. a one-off fee). Omitted, the amount is
    derived per member from the group's pricing: ``Group.base_monthly_price_
    minor`` minus that member's ``GroupMembership.discount``, floored at
    0 so a discount can never make a charge negative."""
    group = repository.get_org_group(db, context.organization_id, req.group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")
    currency = get_settings().default_currency

    if req.amount is not None:
        people = repository.active_group_people(db, req.group_id)
        items = [
            BillingPreviewItem(
                person_id=p.id, display_name=p.display_name, amount=req.amount
            )
            for p in people
        ]
    else:
        if group.base_monthly_price is None:
            raise ConflictError(
                "Grupa nema podešenu cenu; unesite iznos ili podesite cenu grupe.",
                details={"code": "GROUP_PRICE_NOT_SET"},
            )
        base_price = group.base_monthly_price
        members = repository.active_group_members_with_discount(db, req.group_id)
        items = [
            BillingPreviewItem(
                person_id=p.id,
                display_name=p.display_name,
                amount=max(base_price - discount, money.zero()),
            )
            for p, discount in members
        ]

    total = sum((i.amount for i in items), money.zero())
    # The fingerprint covers each member's resolved amount (not just the
    # request), so a roster change OR a pricing/discount change between
    # preview and post both invalidate the hash and force a fresh review.
    fingerprint = {
        "group_id": req.group_id,
        "description": req.description,
        "period_label": req.period_label,
        "currency": currency,
        # Decimals are not JSON-serialisable and their repr is not stable
        # across scales, so the fingerprint uses the wire format.
        "items": [
            {"person_id": i.person_id, "amount": money.format_amount(i.amount)}
            for i in items
        ],
    }
    canonical = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
    preview_hash = hashlib.sha256(canonical.encode()).hexdigest()
    return items, total, currency, preview_hash


def preview(
    db: Session, context: RequestContext, req: BillingPreviewRequest
) -> BillingPreviewResponse:
    items, total, currency, preview_hash = _compute(db, context, req)
    return BillingPreviewResponse(
        preview_hash=preview_hash, currency=currency, total=total, items=items
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
        total=total,
        charge_count=len(items),
    )
    db.add(run)
    db.flush()
    due_date = req.due_date if "due_date" in req.model_fields_set else _period_due_date(
        req.period_label
    )
    for item in items:
        # The id is minted here rather than left to the column default, because
        # the payment reference is derived from it and must be set in the same
        # INSERT (the default would only materialise at flush time). Deriving it
        # from the id also makes it permanent: a re-printed slip always carries
        # the reference the payer already used.
        charge_id = new_id("chg")
        db.add(
            Charge(
                id=charge_id,
                organization_id=context.organization_id,
                person_id=item.person_id,
                billing_run_id=run.id,
                source_type=ChargeSourceType.MEMBERSHIP,
                description=req.description,
                currency=currency,
                amount_due=item.amount,
                due_date=due_date,
                payment_reference=ips_qr.reference_base_from_id(charge_id),
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


def _period_due_date(period_label: str) -> dt.date | None:
    """Last day of the billed month, when ``period_label`` reads as ``YYYY-MM``.

    The label is free text (a school may type "Jesenja sezona"), so anything
    that does not parse yields ``None``. Guessing a due date for an unparseable
    label would put a "dospelo" badge on charges nobody set a deadline for.
    """
    try:
        year_text, month_text = period_label.strip().split("-", 1)
        year, month = int(year_text), int(month_text)
        return dt.date(year, month, calendar.monthrange(year, month)[1])
    except (ValueError, TypeError):
        return None


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
            outstanding=outstanding,
            open_charge_count=open_charge_count,
        )
        for person_id, display_name, currency, outstanding, open_charge_count in rows
    ]
    return Page.build(items, total, params)


def debt_summary(db: Session, context: RequestContext) -> DebtSummaryResponse:
    """PRD 07 M2. Org-wide roll-up of :func:`list_debts`."""
    total, people = repository.debt_summary(db, context.organization_id)
    return DebtSummaryResponse(
        currency=get_settings().default_currency,
        total_outstanding=total,
        people_with_debt=people,
    )


# ---------------------------------------------------------------------------
# Payment slip (uplatnica) with an NBS IPS QR
# ---------------------------------------------------------------------------


def _require_slip_access(db: Session, context: RequestContext, person_id: str) -> None:
    """Who may print a slip for whose charge.

    Staff with the billing area may print any of their school's slips. Everyone
    else may print only their own, or one belonging to a child they are an
    active guardian of , the parent case this endpoint exists for. A caller who
    is neither gets the same not-found a nonexistent charge would give, so the
    endpoint never confirms that another family's charge exists.
    """
    granted = parse_granted_areas(context.granted_areas)
    if PermissionArea.BILLING in effective_areas(context.role_code, granted):
        return
    if person_id == context.person_id:
        return
    if repository.is_guardian_of(
        db, context.organization_id, context.person_id, person_id
    ):
        return
    raise NotFoundError("Zaduženje nije pronađeno.")


def payment_slip(
    db: Session, context: RequestContext, charge_id: str
) -> PaymentSlipResponse:
    """Build the payment-slip data for one charge, including its IPS QR payload.

    The QR is an aid for filling in a payment order and nothing else: the money
    moves from the payer's bank account to the school's, and the charge is only
    marked paid once someone at the school checks the account and records the
    payment. Generating a slip therefore changes no state here at all.

    The amount encoded is what is still *outstanding*, not the original amount:
    re-printing a slip for a partially-paid charge must ask for the remainder,
    never for the full sum again.
    """
    charge = repository.get_charge(db, context.organization_id, charge_id)
    if charge is None:
        raise NotFoundError("Zaduženje nije pronađeno.")
    _require_slip_access(db, context, charge.person_id)
    if charge.status is ChargeStatus.CANCELLED:
        raise ConflictError("Za otkazano zaduženje se ne izdaje uplatnica.")

    outstanding = charge.amount_due - charge.amount_paid
    if outstanding <= 0:
        raise ConflictError("Zaduženje je izmireno, uplatnica nije potrebna.")

    organization = repository.get_organization(db, context.organization_id)
    if organization is None or not organization.bank_account_number:
        raise ConflictError(
            "Škola nema unet broj računa, pa uplatnica ne može biti generisana.",
            details={"code": "PAYEE_ACCOUNT_NOT_SET"},
        )

    payer = repository.get_person(db, charge.person_id)
    payer_name = payer.display_name if payer is not None else ""
    reference = charge.payment_reference or ips_qr.reference_base_from_id(charge.id)

    try:
        payload = ips_qr.build_ips_qr_payload(
            account=organization.bank_account_number,
            payee_name=organization.name,
            payee_address=organization.address,
            payee_city=organization.city,
            amount=outstanding,
            currency=charge.currency,
            purpose=charge.description,
            reference=reference,
            payer_name=payer_name or None,
        )
    except ips_qr.PaymentSlipError as exc:
        raise ConflictError(str(exc), details={"code": "PAYEE_DATA_INVALID"}) from exc

    return PaymentSlipResponse(
        charge_id=charge.id,
        payee_name=organization.name,
        payee_address=organization.address,
        payee_city=organization.city,
        account_number=ips_qr.normalize_account(organization.bank_account_number),
        payer_name=payer_name,
        currency=charge.currency,
        amount=outstanding,
        purpose=charge.description,
        payment_code=ips_qr.DEFAULT_PAYMENT_CODE,
        reference_number=(
            f"{ips_qr.REFERENCE_MODEL}{ips_qr.mod97_reference(reference)}"
        ),
        due_date=charge.due_date,
        ips_qr_payload=payload,
    )


def find_charge_by_reference(
    db: Session, context: RequestContext, reference: str
) -> ChargeResponse:
    """Resolve a "poziv na broj" read off a bank statement back to its charge.

    Accepts what a person actually copies , with or without the ``97`` model
    prefix and its two control digits, and with any punctuation , and matches on
    the stored numeric base. This is the manual-confirmation path: it finds the
    charge, it does not settle it.
    """
    digits = "".join(ch for ch in reference if ch.isdigit())
    candidates = [digits]
    # "97" + 2 control digits + base, and just the control digits + base.
    if digits.startswith(ips_qr.REFERENCE_MODEL):
        candidates.append(digits[len(ips_qr.REFERENCE_MODEL) :])
    candidates.extend(
        candidate[2:] for candidate in list(candidates) if len(candidate) > 2
    )
    for candidate in candidates:
        if not candidate:
            continue
        charge = repository.get_charge_by_reference(db, context.organization_id, candidate)
        if charge is not None:
            return ChargeResponse.model_validate(charge)
    raise NotFoundError("Zaduženje za uneti poziv na broj nije pronađeno.")
