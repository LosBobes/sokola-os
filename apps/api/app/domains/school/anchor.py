"""The M04 school anchor: organization link, locators, and status history.

Three invariants live here, and each one is the kind that holds perfectly well
in a service function until the first import or fixture writes around it, so the
database carries the constraint and this module carries the *transition*:

* a school has exactly one current :class:`OrganizationSchool` link, from
  creation to now, with no gap (§2.3, §3.1.3);
* a school has exactly one active locator of each kind (§2.4, §3.7.1);
* ``School.status`` is the projection of an append-only, gapless
  :class:`SchoolStatusTransition` history (§2.5, §5.2).

What is deliberately *not* here: the SCH-01 command itself. §3.2 requires a
platform actor, an M06 person profile, an M03 TenantSecurityState and an M02
owner nomination, none of which exist in this repository yet — they are Wave 2's
later modules. This module is what those will orchestrate, and what the existing
self-service signup path uses in the meantime (see finding F-12).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.domains.organization.enums import (
    OrganizationSchoolChangeReason,
    OrganizationStatus,
)
from app.domains.organization.models import Organization
from app.domains.school import locator as locator_rules
from app.domains.school.enums import (
    ALLOWED_STATUS_TRANSITIONS,
    LocatorKind,
    LocatorStatus,
    SchoolStatus,
    SchoolStatusReason,
)
from app.domains.school.models import (
    OrganizationSchool,
    School,
    SchoolLocator,
    SchoolStatusTransition,
)
from app.domains.tenancy import security as tenancy
from app.domains.tenancy.enums import TenantInvalidationReason
from app.platform import clock

#: How many times a generated school code is retried before giving up. Eight
#: characters over a 31-symbol alphabet is ~8.5e11 values, so a collision is a
#: coincidence, not a capacity problem — but it is not impossible, and an
#: unhandled unique violation here would surface as a failed signup.
_CODE_ATTEMPTS = 8


def _lock_school(db: Session, school_id: str) -> None:
    """Serialize everything that appends to a school's history.

    Status sequence numbers and organization-link intervals are both "read the
    current tail, write the next one" and both must not interleave. One lock per
    school rather than per table, because a transfer and a deactivation racing
    each other is exactly the case where two separate locks would each be held
    correctly and still produce a school with two current links.
    """
    db.execute(text("SELECT 1 FROM school WHERE id = :id FOR UPDATE"), {"id": school_id})


# ---------------------------------------------------------------------------
# Organization link (§2.3)
# ---------------------------------------------------------------------------


def current_organization_link(db: Session, school_id: str) -> OrganizationSchool | None:
    return db.execute(
        select(OrganizationSchool).where(
            OrganizationSchool.school_id == school_id,
            OrganizationSchool.valid_to.is_(None),
        )
    ).scalar_one_or_none()


def open_organization_link(
    db: Session,
    *,
    school_id: str,
    organization: Organization,
    reason: OrganizationSchoolChangeReason,
    case_reference: str,
    actor_ref: str,
    at: dt.datetime | None = None,
) -> OrganizationSchool:
    """Open the school's first link. Use :func:`transfer_organization` to change one."""
    if organization.status is not OrganizationStatus.ACTIVE:
        raise ConflictError("Organizacija je arhivirana i ne može primiti školu.")
    _lock_school(db, school_id)
    if current_organization_link(db, school_id) is not None:
        raise ConflictError("Škola već ima aktuelnu vezu sa organizacijom.")

    now = at or clock.now()
    link = OrganizationSchool(
        organization_id=organization.id,
        school_id=school_id,
        valid_from=now,
        change_reason_code=reason,
        case_reference=case_reference,
        created_by_actor_ref=actor_ref,
        created_at=now,
    )
    db.add(link)
    db.flush()
    return link


def transfer_organization(
    db: Session,
    *,
    school_id: str,
    organization: Organization,
    reason: OrganizationSchoolChangeReason,
    case_reference: str,
    actor_ref: str,
) -> OrganizationSchool:
    """Close the current link and open the new one **at the same instant**.

    Same instant, not "now and now": a half-open interval that ends where the
    next begins is what makes the history gapless and non-overlapping at once.
    Using two separate clock reads would leave a microsecond in which the school
    belonged to nobody, and that microsecond is what an entitlement or invoice
    lookup would eventually land on.
    """
    if organization.status is not OrganizationStatus.ACTIVE:
        raise ConflictError("Organizacija je arhivirana i ne može primiti školu.")
    if reason is OrganizationSchoolChangeReason.INITIAL_PROVISIONING:
        raise ConflictError("Prenos zahteva razlog prenosa, ne inicijalno dodeljivanje.")

    _lock_school(db, school_id)
    current = current_organization_link(db, school_id)
    if current is None:
        raise ConflictError("Škola nema aktuelnu vezu sa organizacijom.")
    if current.organization_id == organization.id:
        raise ConflictError("Škola je već vezana za ovu organizaciju.")

    effective_at = clock.now()
    if effective_at <= current.valid_from:
        # Two transfers inside one clock tick. Nudging forward keeps the
        # `valid_to > valid_from` contract without inventing a reordering.
        effective_at = current.valid_from + dt.timedelta(microseconds=1)
    current.valid_to = effective_at

    link = OrganizationSchool(
        organization_id=organization.id,
        school_id=school_id,
        valid_from=effective_at,
        change_reason_code=reason,
        case_reference=case_reference,
        created_by_actor_ref=actor_ref,
        created_at=effective_at,
    )
    db.add(link)
    db.flush()
    return link


# ---------------------------------------------------------------------------
# Locators (§2.4)
# ---------------------------------------------------------------------------


def active_locator(db: Session, school_id: str, kind: LocatorKind) -> SchoolLocator | None:
    return db.execute(
        select(SchoolLocator).where(
            SchoolLocator.school_id == school_id,
            SchoolLocator.kind == kind,
            SchoolLocator.status == LocatorStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def resolve_locator(db: Session, kind: LocatorKind, value: str) -> str | None:
    """Which school an active locator points at, or ``None``.

    ``None`` covers both "no such locator" and "retired", and the caller is
    expected to answer both with the same safe-not-found (§3.7.3): telling a
    stranger that a slug exists but is retired is still telling them it exists.
    """
    normalized = (
        locator_rules.normalize_slug(value)
        if kind is LocatorKind.SLUG
        else locator_rules.normalize_school_code(value)
    )
    return db.execute(
        select(SchoolLocator.school_id).where(
            SchoolLocator.kind == kind,
            SchoolLocator.normalized_value == normalized,
            SchoolLocator.status == LocatorStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def _value_is_taken(db: Session, kind: LocatorKind, value: str) -> bool:
    return (
        db.execute(
            select(SchoolLocator.id).where(
                SchoolLocator.kind == kind,
                SchoolLocator.normalized_value == value,
                SchoolLocator.status == LocatorStatus.ACTIVE,
            )
        ).first()
        is not None
    )


def issue_locator(
    db: Session,
    *,
    school_id: str,
    kind: LocatorKind,
    value: str,
    actor_ref: str,
    at: dt.datetime | None = None,
) -> SchoolLocator:
    """Issue the school's first locator of this kind. Rotation is a separate call."""
    if active_locator(db, school_id, kind) is not None:
        raise ConflictError("Škola već ima aktivan lokator ove vrste.")
    normalized = (
        locator_rules.normalize_slug(value)
        if kind is LocatorKind.SLUG
        else locator_rules.normalize_school_code(value)
    )
    if _value_is_taken(db, kind, normalized):
        raise ConflictError("Ova adresa/šifra je već u upotrebi.")

    row = SchoolLocator(
        school_id=school_id,
        kind=kind,
        normalized_value=normalized,
        status=LocatorStatus.ACTIVE,
        valid_from=at or clock.now(),
        created_by_actor_ref=actor_ref,
    )
    db.add(row)
    db.flush()
    return row


def issue_school_code(
    db: Session, *, school_id: str, actor_ref: str, at: dt.datetime | None = None
) -> SchoolLocator:
    """Issue a fresh, random school code, retrying past the improbable collision."""
    for _ in range(_CODE_ATTEMPTS):
        candidate = locator_rules.generate_school_code()
        if not _value_is_taken(db, LocatorKind.SCHOOL_CODE, candidate):
            return issue_locator(
                db,
                school_id=school_id,
                kind=LocatorKind.SCHOOL_CODE,
                value=candidate,
                actor_ref=actor_ref,
                at=at,
            )
    raise ConflictError("Nije moguće dodeliti šifru škole; pokušajte ponovo.")


def rotate_locator(
    db: Session, *, school_id: str, kind: LocatorKind, value: str, actor_ref: str
) -> SchoolLocator:
    """Retire the current locator and issue its replacement, atomically (§3.7.2).

    The old row keeps pointing at the new one. That is deliberately *not* a
    redirect: it records what a URL used to mean so a route can decide between a
    neutral redirect and safe-not-found, which is M03's call and not this
    module's (§3.7.3).
    """
    current = active_locator(db, school_id, kind)
    if current is None:
        raise ConflictError("Škola nema aktivan lokator ove vrste.")

    normalized = (
        locator_rules.normalize_slug(value)
        if kind is LocatorKind.SLUG
        else locator_rules.normalize_school_code(value)
    )
    if normalized == current.normalized_value:
        raise ConflictError("Nova vrednost je jednaka trenutnoj.")
    if _value_is_taken(db, kind, normalized):
        raise ConflictError("Ova adresa/šifra je već u upotrebi.")

    now = clock.now()
    # Retire first, so the partial unique index on (school_id, kind) never sees
    # two active rows even for the duration of the statement.
    current.status = LocatorStatus.RETIRED
    current.retired_at = now if now > current.valid_from else current.valid_from + dt.timedelta(
        microseconds=1
    )
    current.version += 1
    db.flush()

    replacement = SchoolLocator(
        school_id=school_id,
        kind=kind,
        normalized_value=normalized,
        status=LocatorStatus.ACTIVE,
        valid_from=current.retired_at,
        created_by_actor_ref=actor_ref,
    )
    db.add(replacement)
    db.flush()
    current.replaced_by_locator_id = replacement.id
    db.flush()
    return replacement


# ---------------------------------------------------------------------------
# Status history (§2.5, §5.2)
# ---------------------------------------------------------------------------


def _next_sequence_no(db: Session, school_id: str) -> int:
    last = db.execute(
        select(func.max(SchoolStatusTransition.sequence_no)).where(
            SchoolStatusTransition.school_id == school_id
        )
    ).scalar()
    return (last or 0) + 1


def record_creation(
    db: Session,
    *,
    school: School,
    actor_ref: str,
    correlation_id: str,
    at: dt.datetime | None = None,
) -> SchoolStatusTransition:
    """Transition #1: the school begins to exist, with no predecessor status."""
    if _next_sequence_no(db, school.id) != 1:
        raise ConflictError("Škola već ima istoriju statusa.")
    # M03 TEN-05: the security state is established with the school itself, in
    # the same transaction. A school that existed for even one commit without
    # one would be a school whose access version nothing could compare against.
    tenancy.initialize(db, school.id)
    now = at or clock.now()
    row = SchoolStatusTransition(
        school_id=school.id,
        sequence_no=1,
        from_status=None,
        to_status=school.status,
        effective_at=now,
        reason_code=SchoolStatusReason.SCHOOL_CREATED,
        actor_ref=actor_ref,
        correlation_id=correlation_id,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


#: M03 §5.2: which M04 status changes are tenant-wide security events. Both
#: directions are: a school coming back is as much a boundary as one going away.
_INVALIDATING_STATUSES = {
    SchoolStatus.DEACTIVATED: TenantInvalidationReason.SCHOOL_DEACTIVATED,
    SchoolStatus.ACTIVE: TenantInvalidationReason.SCHOOL_REACTIVATED,
}


def transition_status(
    db: Session,
    *,
    school: School,
    to_status: SchoolStatus,
    reason_code: SchoolStatusReason,
    actor_ref: str,
    correlation_id: str,
    reason_note: str | None = None,
    on_behalf_of_person_id: str | None = None,
) -> SchoolStatusTransition:
    """Move the school, appending the transition that is the authority for it.

    The projection (``status``, ``activated_at``, ``deactivated_at``) is updated
    in the same transaction, so there is no window where the column and the
    history disagree.
    """
    _lock_school(db, school.id)
    # Flush first: refresh discards pending attribute changes, and a caller
    # orchestrating several writes in one transaction must not lose theirs. After
    # the flush, the reload sees our own writes plus whatever the lock let through.
    db.flush()
    db.refresh(school)
    from_status = school.status

    if from_status is to_status:
        raise ConflictError(f"Škola je već u statusu {to_status.value}.")
    if (from_status, to_status) not in ALLOWED_STATUS_TRANSITIONS:
        raise ConflictError(
            f"Prelaz {from_status.value} → {to_status.value} nije dozvoljen."
        )

    now = clock.now()
    row = SchoolStatusTransition(
        school_id=school.id,
        sequence_no=_next_sequence_no(db, school.id),
        from_status=from_status,
        to_status=to_status,
        effective_at=now,
        reason_code=reason_code,
        reason_note=reason_note,
        actor_ref=actor_ref,
        on_behalf_of_person_id=on_behalf_of_person_id,
        correlation_id=correlation_id,
        created_at=now,
    )
    db.add(row)

    school.status = to_status
    if to_status is SchoolStatus.ACTIVE:
        # Never rewritten: activated_at is "when did this school first operate",
        # which a later reactivation does not change.
        school.activated_at = school.activated_at or now
        school.deactivated_at = None
    elif to_status is SchoolStatus.DEACTIVATED:
        school.deactivated_at = now
    school.version += 1

    # M03 §5.2 and §14: the tenant access version moves in the *same* business
    # transaction as the status change. Reading `School.status` on every request
    # is what makes a deactivation take effect; this is what additionally lets
    # anything issued earlier — a cached context, a secondary projection, an
    # open channel — be recognised as stale rather than merely be wrong.
    #
    # A reactivation bumps it too. Coming back is as much a security boundary as
    # going away: contexts built while the school was deactivated were built
    # under different rules and must not simply resume.
    if to_status in _INVALIDATING_STATUSES:
        tenancy.invalidate(
            db,
            school.id,
            reason_code=_INVALIDATING_STATUSES[to_status],
            correlation_id=correlation_id,
            now=now,
        )

    db.flush()
    return row


def status_history(db: Session, school_id: str) -> list[SchoolStatusTransition]:
    return list(
        db.execute(
            select(SchoolStatusTransition)
            .where(SchoolStatusTransition.school_id == school_id)
            .order_by(SchoolStatusTransition.sequence_no)
        )
        .scalars()
        .all()
    )
