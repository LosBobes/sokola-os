"""M07 §7.1: `PAY-01`..`PAY-04` — who pays, and on what grounds.

The same §7 contract as the other two groups. What differs is the rule in
§2.5 and §3.1 that has no counterpart in the guardian group: a payer must have
a **basis**.

An adult in the child's own family is the ordinary case. A payer in family A
paying for a child in family B is refused with
`M07_PAYER_BASIS_INVALID` — unless the school ran the separate sponsor process
and recorded `SPONSOR_VERIFIED`, which is the one route by which someone
outside the household may pay at all. Checking that reads two
`family_membership` rows, so it is a service rule and could not be a
constraint.

What this module must never do is imply access. §3.7 says a payer link grants
"samo M12 finansijskim operacijama koje izričito prihvataju `PAYER_CHILD_LINK`
basis", and M05 §3.2 point 9 that a `PAYER` basis "nikad ne daje
attendance/document/health/profile/guardian pravo". Nothing here reads or
returns anything about the child beyond the id the link already names.

`PAY-05` and `PAY-06` are in `primary_payer_commands`, for the same reason the
guardian group is split: a different question, and a size ratchet that now
covers every behaviour module.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import (
    InvalidRelationshipTransitionError,
    NotFoundError,
    RelationshipExistsError,
    ValidationFailedError,
)
from app.domains.family.commands_support import (
    check_version,
    record,
    refuse_self_decision,
)
from app.domains.family.enums import (
    PAYER_LINK_ACTIVATED_EVENT,
    PAYER_LINK_REVOKED_EVENT,
    DesignationStatus,
    FamilyMembershipStatus,
    FamilyStatus,
    LinkKind,
    LinkStatus,
    PayerBasisKind,
    VerificationMethod,
)
from app.domains.family.models import (
    Family,
    FamilyMembership,
    PayerChildLink,
    PrimaryPayerDesignation,
    RelationshipVerificationRecord,
)
from app.domains.school.enums import MembershipStatus, MembershipType
from app.domains.school.models import SchoolMembership
from app.platform import clock
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue

_OPEN = (LinkStatus.PENDING_VERIFICATION, LinkStatus.ACTIVE)
#: §2.5: a payer holds one of these, not a single pinned type. A payer need not
#: be a guardian — that is the entity's reason for existing — and a school
#: records a non-guardian payer as a `CONTACT`.
_PAYER_TYPES = (MembershipType.CONTACT, MembershipType.GUARDIAN)


def require_payer_link(
    db: Session, school_id: str, link_id: str, *, for_update: bool = False
) -> PayerChildLink:
    stmt = select(PayerChildLink).where(
        PayerChildLink.school_id == school_id, PayerChildLink.id == link_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    link = db.execute(stmt).scalar_one_or_none()
    if link is None:
        raise NotFoundError("Veza nije pronađena.")
    return link


def _open_membership(
    db: Session,
    school_id: str,
    person_id: str,
    membership_types: tuple[MembershipType, ...],
) -> SchoolMembership:
    membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.person_id == person_id,
            SchoolMembership.membership_type.in_(membership_types),
            SchoolMembership.status != MembershipStatus.TERMINATED,
        )
    ).scalars().first()
    if membership is None:
        raise ValidationFailedError(
            "Osoba nema otvoreno članstvo odgovarajućeg tipa u ovoj školi."
        )
    return membership


def _refuse_invalid_basis(
    db: Session,
    *,
    school_id: str,
    family_id: str,
    payer_person_id: str,
    child_person_id: str,
    basis_kind: PayerBasisKind,
) -> None:
    """§2.5, §3.1: "Payer je u Family A, dete samo u Family B" → 422.

    `SPONSOR_VERIFIED` is the deliberate exception and the only one. §3.1 calls
    it an "eksplicitno verifikovan sponsor proces", so a caller that wants to
    record a payer from outside the household has to say so in the row rather
    than have it inferred — which is what keeps the ordinary case honest.
    """
    family = db.execute(
        select(Family).where(Family.school_id == school_id, Family.id == family_id)
    ).scalar_one_or_none()
    if family is None:
        raise NotFoundError("Porodica nije pronađena.")
    if family.status is not FamilyStatus.ACTIVE:
        raise InvalidRelationshipTransitionError(
            "Platilačka veza se ne vezuje za arhiviranu porodičnu grupu."
        )

    if basis_kind is PayerBasisKind.SPONSOR_VERIFIED:
        return

    members = set(
        db.execute(
            select(FamilyMembership.person_id).where(
                FamilyMembership.school_id == school_id,
                FamilyMembership.family_id == family_id,
                FamilyMembership.status == FamilyMembershipStatus.ACTIVE,
                FamilyMembership.person_id.in_((payer_person_id, child_person_id)),
            )
        )
        .scalars()
        .all()
    )
    if {payer_person_id, child_person_id} - members:
        raise ValidationFailedError(
            "Osnov za platioca nije potvrđen: obe osobe moraju biti aktivni "
            "članovi porodične grupe, osim kod verifikovanog sponzorstva."
        )


def request_payer_child_link(
    db: Session,
    *,
    school_id: str,
    payer_person_id: str,
    child_person_id: str,
    family_id: str,
    basis_kind: PayerBasisKind,
    actor_account_id: str,
    request_id: str,
    actor_person_id: str | None = None,
) -> PayerChildLink:
    """`PAY-01`. §5.3: valid M06 types, no open duplicate, and a basis.

    Note what is *not* refused: the payer and the child being the same person.
    §2.3 forbids that for a guardian link and §2.5 says nothing of the kind,
    which reads as deliberate — an adult who trains at the school and pays
    their own fees holds both a `PARTICIPANT` and a `CONTACT` membership. The
    asymmetry is recorded rather than decided.
    """
    guard = idempotency.begin(
        db,
        school_id,
        "m07.payer_link.request",
        request_id,
        {
            "payer_person_id": payer_person_id,
            "child_person_id": child_person_id,
            "family_id": family_id,
            "basis_kind": basis_kind.value,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return require_payer_link(db, school_id, guard.replay["body"]["id"])

    payer_membership = _open_membership(db, school_id, payer_person_id, _PAYER_TYPES)
    child_membership = _open_membership(
        db, school_id, child_person_id, (MembershipType.PARTICIPANT,)
    )
    _refuse_invalid_basis(
        db,
        school_id=school_id,
        family_id=family_id,
        payer_person_id=payer_person_id,
        child_person_id=child_person_id,
        basis_kind=basis_kind,
    )

    open_link = db.execute(
        select(PayerChildLink).where(
            PayerChildLink.school_id == school_id,
            PayerChildLink.payer_person_id == payer_person_id,
            PayerChildLink.child_person_id == child_person_id,
            PayerChildLink.status.in_(_OPEN),
        )
    ).scalar_one_or_none()
    if open_link is not None:
        raise RelationshipExistsError("Otvorena veza za ovaj par već postoji.")

    link = PayerChildLink(
        school_id=school_id,
        payer_person_id=payer_person_id,
        child_person_id=child_person_id,
        payer_school_membership_id=payer_membership.id,
        child_school_membership_id=child_membership.id,
        payer_membership_type=payer_membership.membership_type.value,
        child_membership_type=MembershipType.PARTICIPANT.value,
        family_id=family_id,
        basis_kind=basis_kind,
        status=LinkStatus.PENDING_VERIFICATION,
        requested_by_account_id=actor_account_id,
        requested_at=clock.now(),
        version=1,
    )
    db.add(link)
    db.flush()

    record(
        db,
        school_id=school_id,
        entity_type="payer_child_link",
        action="m07.payer_link.request",
        entity_id=link.id,
        summary="Zatražena je platilačka veza.",
        actor_person_id=actor_person_id,
        context={"basis_kind": basis_kind.value},
    )
    idempotency.complete(db, guard, status=201, body={"id": link.id})
    return link


def verify_and_activate_payer_link(
    db: Session,
    *,
    school_id: str,
    link_id: str,
    expected_version: int,
    verification_method: VerificationMethod,
    policy_version: str,
    actor_account_id: str,
    request_id: str,
    evidence_reference_digest: str | None = None,
    actor_person_id: str | None = None,
    correlation_id: str | None = None,
) -> PayerChildLink:
    """`PAY-02`. §3.5: ACTIVE and its one immutable proof, atomically."""
    # §2.4 makes `policy_version` mandatory. An activation nobody can
    # trace to a checking procedure is not evidence that one happened —
    # and a blank string satisfies a NOT NULL column perfectly well.
    if not policy_version.strip():
        raise ValidationFailedError("Verzija procedure provere je obavezna.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.payer_link.activate",
        request_id,
        {
            "link_id": link_id,
            "expected_version": expected_version,
            "verification_method": verification_method.value,
            "policy_version": policy_version,
            "evidence_reference_digest": evidence_reference_digest,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return require_payer_link(db, school_id, link_id)

    link = require_payer_link(db, school_id, link_id, for_update=True)
    if link.status is not LinkStatus.PENDING_VERIFICATION:
        raise InvalidRelationshipTransitionError(
            "Aktivira se samo veza koja čeka proveru."
        )
    check_version(link.version, expected_version)
    refuse_self_decision(
        db,
        requested_by_account_id=link.requested_by_account_id,
        decider_account_id=actor_account_id,
        party_person_ids=(link.payer_person_id, link.child_person_id),
    )

    moment = clock.now()
    link.status = LinkStatus.ACTIVE
    link.activated_at = moment
    link.decision_by_account_id = actor_account_id
    link.version += 1

    db.add(
        RelationshipVerificationRecord(
            school_id=school_id,
            link_kind=LinkKind.PAYER_CHILD,
            payer_child_link_id=link.id,
            verification_method=verification_method,
            evidence_reference_digest=evidence_reference_digest,
            verified_by_account_id=actor_account_id,
            verified_at=moment,
            policy_version=policy_version,
        )
    )
    db.flush()

    record(
        db,
        school_id=school_id,
        entity_type="payer_child_link",
        action="m07.payer_link.activate",
        entity_id=link.id,
        summary="Platilačka veza je potvrđena i aktivirana.",
        actor_person_id=actor_person_id,
        context={
            "verification_method": verification_method.value,
            "policy_version": policy_version,
        },
    )
    _emit(
        db,
        event_type=PAYER_LINK_ACTIVATED_EVENT,
        school_id=school_id,
        link=link,
        correlation_id=correlation_id,
    )
    idempotency.complete(db, guard, status=200, body={"id": link.id})
    return link


def reject_payer_link(
    db: Session,
    *,
    school_id: str,
    link_id: str,
    expected_version: int,
    reason_code: str,
    actor_account_id: str,
    request_id: str,
    actor_person_id: str | None = None,
) -> PayerChildLink:
    """`PAY-03`. No event, for the reason `GRD-03` gives: nothing downstream
    ever acted on a pending link."""
    if not reason_code.strip():
        raise ValidationFailedError("Razlog odbijanja je obavezan.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.payer_link.reject",
        request_id,
        {
            "link_id": link_id,
            "expected_version": expected_version,
            "reason_code": reason_code,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return require_payer_link(db, school_id, link_id)

    link = require_payer_link(db, school_id, link_id, for_update=True)
    if link.status is not LinkStatus.PENDING_VERIFICATION:
        raise InvalidRelationshipTransitionError(
            "Odbija se samo veza koja čeka proveru."
        )
    check_version(link.version, expected_version)
    refuse_self_decision(
        db,
        requested_by_account_id=link.requested_by_account_id,
        decider_account_id=actor_account_id,
        party_person_ids=(link.payer_person_id, link.child_person_id),
    )

    link.status = LinkStatus.REJECTED
    link.rejected_at = clock.now()
    link.decision_by_account_id = actor_account_id
    link.decision_reason_code = reason_code
    link.version += 1
    db.flush()

    record(
        db,
        school_id=school_id,
        entity_type="payer_child_link",
        action="m07.payer_link.reject",
        entity_id=link.id,
        summary="Platilačka veza je odbijena.",
        actor_person_id=actor_person_id,
        context={"reason_code": reason_code},
    )
    idempotency.complete(db, guard, status=200, body={"id": link.id})
    return link


def revoke_payer_link(
    db: Session,
    *,
    school_id: str,
    link_id: str,
    expected_version: int,
    reason_code: str,
    actor_account_id: str,
    request_id: str,
    actor_person_id: str | None = None,
    correlation_id: str | None = None,
) -> PayerChildLink:
    """`PAY-04`. §3.10: the link and every primary-payer designation on it, in
    one transaction.

    Revoking here removes a *billing* relationship and nothing else — §3.7
    already kept it from carrying anything else. The other ACTIVE payer links
    for the same child are untouched, which §2.5 requires: several payers per
    child are allowed and M12 decides how an obligation is split.
    """
    if not reason_code.strip():
        raise ValidationFailedError("Razlog opoziva je obavezan.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.payer_link.revoke",
        request_id,
        {
            "link_id": link_id,
            "expected_version": expected_version,
            "reason_code": reason_code,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return require_payer_link(db, school_id, link_id)

    link = require_payer_link(db, school_id, link_id, for_update=True)
    if link.status not in _OPEN:
        raise InvalidRelationshipTransitionError("Veza je već u konačnom stanju.")
    check_version(link.version, expected_version)

    moment = clock.now()
    link.status = LinkStatus.REVOKED
    link.revoked_at = moment
    link.decision_by_account_id = actor_account_id
    link.decision_reason_code = reason_code
    link.version += 1

    closed = close_payer_designations_for(
        db,
        school_id=school_id,
        link_id=link.id,
        moment=moment,
        reason_code="LINK_REVOKED",
    )
    db.flush()

    record(
        db,
        school_id=school_id,
        entity_type="payer_child_link",
        action="m07.payer_link.revoke",
        entity_id=link.id,
        summary="Platilačka veza je opozvana.",
        actor_person_id=actor_person_id,
        context={"reason_code": reason_code, "closed_designations": closed},
    )
    _emit(
        db,
        event_type=PAYER_LINK_REVOKED_EVENT,
        school_id=school_id,
        link=link,
        correlation_id=correlation_id,
        extra={"closed_designations": closed},
    )
    idempotency.complete(db, guard, status=200, body={"id": link.id})
    return link


def close_payer_designations_for(
    db: Session,
    *,
    school_id: str,
    link_id: str,
    moment: dt.datetime,
    reason_code: str,
) -> int:
    rows = (
        db.execute(
            select(PrimaryPayerDesignation)
            .where(
                PrimaryPayerDesignation.school_id == school_id,
                PrimaryPayerDesignation.payer_child_link_id == link_id,
                PrimaryPayerDesignation.status == DesignationStatus.ACTIVE,
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.status = DesignationStatus.REVOKED
        row.ended_at = moment
        row.end_reason_code = reason_code
        row.version += 1
    return len(rows)


def _emit(
    db: Session,
    *,
    event_type: str,
    school_id: str,
    link: PayerChildLink,
    correlation_id: str | None,
    extra: dict[str, Any] | None = None,
) -> None:
    """§7.3: opaque IDs, status, version, reason code.

    `basis_kind` stays out. "This adult pays for this child because they are
    family" is a statement about the relationship, and §4 keeps those out of
    events — the same reason the guardian events carry no `relationship_kind`.
    """
    payload: dict[str, Any] = {
        "school_id": school_id,
        "payer_child_link_id": link.id,
        "payer_person_id": link.payer_person_id,
        "child_person_id": link.child_person_id,
        "status": link.status.value,
        "version": link.version,
        "reason_code": link.decision_reason_code,
        "correlation_id": correlation_id,
        "dedupe_key": f"{link.id}:{link.version}",
    }
    if extra:
        payload.update(extra)
    enqueue(db, event_type=event_type, payload=payload, school_id=school_id)


__all__ = [
    "close_payer_designations_for",
    "reject_payer_link",
    "request_payer_child_link",
    "require_payer_link",
    "revoke_payer_link",
    "verify_and_activate_payer_link",
]
