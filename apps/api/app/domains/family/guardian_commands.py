"""M07 §7.1: `GRD-01`..`GRD-04` — verifying and withdrawing guardianship.

Four of the GRD group's six commands. `GRD-05` and `GRD-06`, which decide who
the school calls first, live in `primary_contact_commands` — a different
question (who *is* a guardian versus which guardian comes first) and, once the
architecture gate's size ratchet started covering command modules, a different
file whether or not one wanted it.

These four commands They carry the same §7 contract the
FAM group does (stable `request_id`, `expected_version`, one transaction, no
commit inside), so only what is different is explained here.

Named `guardian_commands` rather than folded into `service.py` because the two
groups together would pass the architecture gate's size ratchet — and this
change widens that ratchet to cover any behaviour module rather than only
files literally called `service.py`, so the split buys separation without
buying an exemption.

Three rules live here that no constraint could hold:

* **§5.3 / §3.6, the distinct approver.** The account that approves cannot be
  the account that asked, and cannot belong to the person whose link is being
  decided. A database cannot know which human an account belongs to; this can,
  because M01 gives an account its person.
* **§3.5, atomic activation.** A link becomes ACTIVE and its single immutable
  verification record appears in the same transaction. Either both or neither,
  or there is an active guardianship nobody can account for.
* **§3.10, revocation closes designations.** Revoking a link and closing every
  primacy resting on it is one transaction. A primary contact pointing at a
  revoked link is worse than none: §3.1 allows zero primary contacts and calls
  a stale one the thing that must never happen.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import (
    ForbiddenError,
    InvalidRelationshipTransitionError,
    NotFoundError,
    RelationshipExistsError,
    StaleVersionError,
    ValidationFailedError,
)
from app.domains.family.enums import (
    GUARDIAN_LINK_ACTIVATED_EVENT,
    GUARDIAN_LINK_REVOKED_EVENT,
    DesignationStatus,
    LinkKind,
    LinkStatus,
    RelationshipKind,
    VerificationMethod,
)
from app.domains.family.models import (
    GuardianChildLink,
    PrimaryGuardianContactDesignation,
    RelationshipVerificationRecord,
)
from app.domains.identity.auth_models import UserAccount
from app.domains.school.enums import MembershipStatus, MembershipType
from app.domains.school.models import SchoolMembership
from app.platform import clock
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue

_OPEN = (LinkStatus.PENDING_VERIFICATION, LinkStatus.ACTIVE)


def require_link(
    db: Session, school_id: str, link_id: str, *, for_update: bool = False
) -> GuardianChildLink:
    stmt = select(GuardianChildLink).where(
        GuardianChildLink.school_id == school_id, GuardianChildLink.id == link_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    link = db.execute(stmt).scalar_one_or_none()
    if link is None:
        # §4: unknown, cross-tenant and not-allowed-to-know give one answer.
        raise NotFoundError("Veza nije pronađena.")
    return link


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise StaleVersionError("Podaci su u međuvremenu izmenjeni.")


def _open_membership(
    db: Session, school_id: str, person_id: str, membership_type: MembershipType
) -> SchoolMembership:
    membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.person_id == person_id,
            SchoolMembership.membership_type == membership_type,
            SchoolMembership.status != MembershipStatus.TERMINATED,
        )
    ).scalars().first()
    if membership is None:
        # §6 `M07_MEMBERSHIP_TYPE_MISMATCH`, phrased so it says nothing about
        # which of the two people is the problem.
        raise ValidationFailedError(
            "Osoba nema otvoreno članstvo odgovarajućeg tipa u ovoj školi."
        )
    return membership


def _person_for_account(db: Session, account_id: str) -> str | None:
    return db.execute(
        select(UserAccount.person_id).where(UserAccount.id == account_id)
    ).scalar_one_or_none()


def _refuse_self_verification(
    db: Session, link: GuardianChildLink, decider_account_id: str
) -> None:
    """§3.6 / §6 `M07_SELF_VERIFICATION_FORBIDDEN`, plus §5.3's distinct approver.

    Two separate checks that read as one rule. The account must differ from the
    requester's — otherwise "two people looked at this" is one person twice —
    **and** it must not belong to either person in the link, or a guardian
    approves their own guardianship through a second account they happen to
    hold.

    The second check is why this cannot be a constraint: it needs M01 to say
    which person an account belongs to, and a CHECK sees only ids.
    """
    if decider_account_id == link.requested_by_account_id:
        raise ForbiddenError("Odluku ne može doneti nalog koji je podneo zahtev.")
    decider_person_id = _person_for_account(db, decider_account_id)
    if decider_person_id is not None and decider_person_id in (
        link.guardian_person_id,
        link.child_person_id,
    ):
        raise ForbiddenError("Nalog ne može odlučivati o sopstvenoj vezi.")


def request_guardian_child_link(
    db: Session,
    *,
    school_id: str,
    guardian_person_id: str,
    child_person_id: str,
    relationship_kind: RelationshipKind,
    actor_account_id: str,
    request_id: str,
    actor_person_id: str | None = None,
) -> GuardianChildLink:
    """`GRD-01 RequestGuardianChildLink`. §5.3: valid M06 types, no open duplicate.

    Always lands in `PENDING_VERIFICATION`. §1.2 forbids a parent activating
    another guardian themselves, and the way that is guaranteed is that no path
    creates an ACTIVE link — activation is `GRD-02` and needs a second account.
    """
    if guardian_person_id == child_person_id:
        raise ValidationFailedError("Staratelj i dete ne mogu biti ista osoba.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.guardian_link.request",
        request_id,
        {
            "guardian_person_id": guardian_person_id,
            "child_person_id": child_person_id,
            "relationship_kind": relationship_kind.value,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return require_link(db, school_id, guard.replay["body"]["id"])

    guardian_membership = _open_membership(
        db, school_id, guardian_person_id, MembershipType.GUARDIAN
    )
    child_membership = _open_membership(
        db, school_id, child_person_id, MembershipType.PARTICIPANT
    )

    open_link = db.execute(
        select(GuardianChildLink).where(
            GuardianChildLink.school_id == school_id,
            GuardianChildLink.guardian_person_id == guardian_person_id,
            GuardianChildLink.child_person_id == child_person_id,
            GuardianChildLink.status.in_(_OPEN),
        )
    ).scalar_one_or_none()
    if open_link is not None:
        raise RelationshipExistsError("Otvorena veza za ovaj par već postoji.")

    link = GuardianChildLink(
        school_id=school_id,
        guardian_person_id=guardian_person_id,
        child_person_id=child_person_id,
        guardian_school_membership_id=guardian_membership.id,
        child_school_membership_id=child_membership.id,
        guardian_membership_type=MembershipType.GUARDIAN.value,
        child_membership_type=MembershipType.PARTICIPANT.value,
        relationship_kind=relationship_kind,
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
        action="m07.guardian_link.request",
        entity_id=link.id,
        summary="Zatražena je starateljska veza.",
        actor_person_id=actor_person_id,
        context={"relationship_kind": relationship_kind.value},
    )
    idempotency.complete(db, guard, status=201, body={"id": link.id})
    return link


def verify_and_activate_guardian_link(
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
) -> GuardianChildLink:
    """`GRD-02`. §3.5: ACTIVE and its one immutable proof, atomically.

    Both rows or neither. A link that went ACTIVE without its record would be
    an active guardianship nobody can account for afterwards, and a record
    without the activation would claim a check that granted nothing.
    """
    guard = idempotency.begin(
        db,
        school_id,
        "m07.guardian_link.activate",
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
        return require_link(db, school_id, link_id)

    link = require_link(db, school_id, link_id, for_update=True)
    if link.status is not LinkStatus.PENDING_VERIFICATION:
        raise InvalidRelationshipTransitionError(
            "Aktivira se samo veza koja čeka proveru."
        )
    check_version(link.version, expected_version)
    _refuse_self_verification(db, link, actor_account_id)

    moment = clock.now()
    link.status = LinkStatus.ACTIVE
    link.activated_at = moment
    link.decision_by_account_id = actor_account_id
    link.version += 1

    db.add(
        RelationshipVerificationRecord(
            school_id=school_id,
            link_kind=LinkKind.GUARDIAN_CHILD,
            guardian_child_link_id=link.id,
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
        action="m07.guardian_link.activate",
        entity_id=link.id,
        summary="Starateljska veza je potvrđena i aktivirana.",
        actor_person_id=actor_person_id,
        # §4: a method code and a policy version, never the evidence itself.
        context={
            "verification_method": verification_method.value,
            "policy_version": policy_version,
        },
    )
    _emit(
        db,
        event_type=GUARDIAN_LINK_ACTIVATED_EVENT,
        school_id=school_id,
        link=link,
        correlation_id=correlation_id,
    )
    idempotency.complete(db, guard, status=200, body={"id": link.id})
    return link


def reject_guardian_link(
    db: Session,
    *,
    school_id: str,
    link_id: str,
    expected_version: int,
    reason_code: str,
    actor_account_id: str,
    request_id: str,
    actor_person_id: str | None = None,
) -> GuardianChildLink:
    """`GRD-03`. §5.3: reason required, and the same distinct-approver rule.

    No outbox event: §7.3 lists `GuardianLinkActivated|Revoked` and not a
    rejection. Nothing downstream ever acted on this link, so there is nothing
    to tell anyone to stop doing — and an event announcing that a named adult
    was refused guardianship of a named child is a disclosure with no consumer.
    """
    if not reason_code.strip():
        raise ValidationFailedError("Razlog odbijanja je obavezan.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.guardian_link.reject",
        request_id,
        {
            "link_id": link_id,
            "expected_version": expected_version,
            "reason_code": reason_code,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return require_link(db, school_id, link_id)

    link = require_link(db, school_id, link_id, for_update=True)
    if link.status is not LinkStatus.PENDING_VERIFICATION:
        raise InvalidRelationshipTransitionError(
            "Odbija se samo veza koja čeka proveru."
        )
    check_version(link.version, expected_version)
    _refuse_self_verification(db, link, actor_account_id)

    link.status = LinkStatus.REJECTED
    link.rejected_at = clock.now()
    link.decision_by_account_id = actor_account_id
    link.decision_reason_code = reason_code
    link.version += 1
    db.flush()

    record(
        db,
        school_id=school_id,
        action="m07.guardian_link.reject",
        entity_id=link.id,
        summary="Starateljska veza je odbijena.",
        actor_person_id=actor_person_id,
        context={"reason_code": reason_code},
    )
    idempotency.complete(db, guard, status=200, body={"id": link.id})
    return link


def revoke_guardian_link(
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
) -> GuardianChildLink:
    """`GRD-04`. §3.10: the link and every designation on it, one transaction.

    A primary contact still pointing at a revoked link is the precise thing
    §3.1 forbids — it allows a child to have *no* primary contact and says the
    one state that must never occur is a stale one. So the designations close
    here rather than in a consumer that might lag.

    §3.12 is the reason this does not wait for anything: a request arriving
    after this commit must not pass on a cached answer. The link's `version`
    is §2.3's "authorization version", and it moves in this transaction; the
    outbox event carries the new value so projections can catch up, but the
    refusal does not depend on the event being delivered.

    Deliberately *not* a tenant-wide invalidation. M03's
    `tenancy.security.invalidate` bumps the school's access version and logs
    out everyone in it; using it because one family's arrangement changed
    would be an outage dressed as a security measure.
    """
    if not reason_code.strip():
        raise ValidationFailedError("Razlog opoziva je obavezan.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.guardian_link.revoke",
        request_id,
        {
            "link_id": link_id,
            "expected_version": expected_version,
            "reason_code": reason_code,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return require_link(db, school_id, link_id)

    link = require_link(db, school_id, link_id, for_update=True)
    if link.status not in _OPEN:
        raise InvalidRelationshipTransitionError("Veza je već u konačnom stanju.")
    check_version(link.version, expected_version)

    moment = clock.now()
    link.status = LinkStatus.REVOKED
    link.revoked_at = moment
    link.decision_by_account_id = actor_account_id
    link.decision_reason_code = reason_code
    link.version += 1

    closed = close_designations_for(
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
        action="m07.guardian_link.revoke",
        entity_id=link.id,
        summary="Starateljska veza je opozvana.",
        actor_person_id=actor_person_id,
        context={"reason_code": reason_code, "closed_designations": closed},
    )
    _emit(
        db,
        event_type=GUARDIAN_LINK_REVOKED_EVENT,
        school_id=school_id,
        link=link,
        correlation_id=correlation_id,
        extra={"closed_designations": closed},
    )
    idempotency.complete(db, guard, status=200, body={"id": link.id})
    return link


def close_designations_for(
    db: Session,
    *,
    school_id: str,
    link_id: str,
    moment: dt.datetime,
    reason_code: str,
) -> int:
    rows = (
        db.execute(
            select(PrimaryGuardianContactDesignation)
            .where(
                PrimaryGuardianContactDesignation.school_id == school_id,
                PrimaryGuardianContactDesignation.guardian_child_link_id == link_id,
                PrimaryGuardianContactDesignation.status == DesignationStatus.ACTIVE,
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


def record(
    db: Session,
    *,
    school_id: str,
    action: str,
    entity_id: str,
    summary: str,
    entity_type: str = "guardian_child_link",
    actor_person_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """One audit entry in the caller's transaction, with M07's data class.

    Shared with `primary_contact_commands` so both halves of the GRD group
    classify their entries the same way. A relationship decision filed under a
    different class is one a later privacy review will not find.
    """
    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        school_id=school_id,
        actor_person_id=actor_person_id,
        context=context,
    )


def _emit(
    db: Session,
    *,
    event_type: str,
    school_id: str,
    link: GuardianChildLink,
    correlation_id: str | None,
    extra: dict[str, Any] | None = None,
) -> None:
    """§7.3: opaque IDs, status, version, reason code. Nothing else.

    In particular no names and no `relationship_kind` — "X is the legal
    guardian of Y" is exactly the sentence §4 keeps out of events.
    """
    payload: dict[str, Any] = {
        "school_id": school_id,
        "guardian_child_link_id": link.id,
        "guardian_person_id": link.guardian_person_id,
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
    "check_version",
    "close_designations_for",
    "record",
    "reject_guardian_link",
    "request_guardian_child_link",
    "require_link",
    "revoke_guardian_link",
    "verify_and_activate_guardian_link",
]
