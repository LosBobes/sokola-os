"""Membership transitions (M06 §5.1, MEM-01..05).

The two rules worth stating before the code:

**A terminated membership is terminal, and coming back is a new row.** Reviving
the row would overwrite when the person was previously a member, and that
history is what ``is_first_activation`` and every retrospective count depend on.
It is also the only reason a school can answer "did this family leave and come
back, or have they been with us throughout".

**``is_first_activation`` is derived, then frozen.** It answers "is this the
first time this person has ever been a member of this school under this type",
so it is computed from the history at activation and never recomputed — a later
episode must not retroactively make an earlier one look like a return.

What is *not* here: the M05 owner guard §3.9 requires before terminating a
membership that carries the last active OWNER role. M06 must not import M05, so
the application use-case that owns both locks them in a stable order and calls
the owner invariant itself. :func:`ensure_termination_allowed` is where that
call belongs, and it says so rather than pretending the check has happened.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.domains.school.enums import (
    ALLOWED_MEMBERSHIP_TRANSITIONS,
    MembershipStatus,
    MembershipType,
)
from app.domains.school.models import SchoolMembership
from app.platform import clock


def open_episode(
    db: Session, school_id: str, person_id: str, membership_type: MembershipType
) -> SchoolMembership | None:
    """The membership of this type that is currently open, if any."""
    return db.execute(
        select(SchoolMembership).where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.person_id == person_id,
            SchoolMembership.membership_type == membership_type,
            SchoolMembership.status != MembershipStatus.TERMINATED,
        )
    ).scalar_one_or_none()


def _has_earlier_activation(
    db: Session, school_id: str, person_id: str, membership_type: MembershipType
) -> bool:
    """Has this natural key ever been activated before?

    Counts any row that reached activation, terminated or not: a returning
    member's earlier episode is exactly what makes this one not a first.
    """
    return bool(
        db.execute(
            select(func.count())
            .select_from(SchoolMembership)
            .where(
                SchoolMembership.school_id == school_id,
                SchoolMembership.person_id == person_id,
                SchoolMembership.membership_type == membership_type,
                SchoolMembership.is_first_activation.is_(True),
            )
        ).scalar_one()
    )


def create_membership(
    db: Session,
    *,
    school_id: str,
    person_id: str,
    membership_type: MembershipType,
    start_date: dt.date | None = None,
    status: MembershipStatus = MembershipStatus.DRAFT,
) -> SchoolMembership:
    """MEM-01. Refuses a second open episode of the same natural key (§3.1)."""
    if status is MembershipStatus.TERMINATED:
        raise ConflictError("Članstvo se ne kreira kao završeno.")
    if open_episode(db, school_id, person_id, membership_type) is not None:
        raise ConflictError("Osoba već ima otvoreno članstvo ovog tipa u ovoj školi.")

    membership = SchoolMembership(
        school_id=school_id,
        person_id=person_id,
        membership_type=membership_type,
        status=status,
        start_date=start_date or clock.now().date(),
    )
    if status is MembershipStatus.ACTIVE:
        membership.is_first_activation = not _has_earlier_activation(
            db, school_id, person_id, membership_type
        )
    db.add(membership)
    db.flush()
    return membership


def _transition(membership: SchoolMembership, to_status: MembershipStatus) -> None:
    if (membership.status, to_status) not in ALLOWED_MEMBERSHIP_TRANSITIONS:
        raise ConflictError(
            f"Prelaz {membership.status.value} → {to_status.value} nije dozvoljen."
        )


def activate_membership(db: Session, membership: SchoolMembership) -> SchoolMembership:
    """MEM-02. Sets ``is_first_activation`` once, from the history as it stands."""
    _transition(membership, MembershipStatus.ACTIVE)
    was_draft = membership.status is MembershipStatus.DRAFT

    membership.status = MembershipStatus.ACTIVE
    membership.suspension_reason_code = None
    if was_draft:
        # Only a first activation decides this. Resuming from SUSPENDED is the
        # same episode continuing and must not re-answer the question.
        membership.is_first_activation = not _has_earlier_activation(
            db, membership.school_id, membership.person_id, membership.membership_type
        )
    membership.version += 1
    db.flush()
    return membership


def suspend_membership(
    db: Session, membership: SchoolMembership, *, reason_code: str
) -> SchoolMembership:
    """MEM-03. §3.8: immediately ineffective for M03/M05, event or no event."""
    _transition(membership, MembershipStatus.SUSPENDED)
    if not reason_code:
        raise ConflictError("Suspenzija zahteva razlog.")
    membership.status = MembershipStatus.SUSPENDED
    membership.suspension_reason_code = reason_code
    membership.version += 1
    db.flush()
    return membership


def ensure_termination_allowed(membership: SchoolMembership) -> None:
    """Hook for the M05 owner invariant (§3.9), which M06 may not call itself.

    The application use-case that owns both modules locks the relevant M05
    assignments and this membership in a stable order, calls M05's owner
    invariant, and only then terminates here. This function exists so that
    sequencing has a named place rather than being an unwritten convention.
    """
    return None


def terminate_membership(
    db: Session,
    membership: SchoolMembership,
    *,
    reason_code: str,
    end_date: dt.date | None = None,
) -> SchoolMembership:
    """MEM-05. Terminal: a returning member gets a new row, never this one."""
    _transition(membership, MembershipStatus.TERMINATED)
    if not reason_code:
        raise ConflictError("Prekid članstva zahteva razlog.")
    ensure_termination_allowed(membership)

    closing = end_date or clock.now().date()
    if closing < membership.start_date:
        raise ConflictError("Datum završetka ne može biti pre datuma početka.")

    membership.status = MembershipStatus.TERMINATED
    membership.termination_reason_code = reason_code
    membership.suspension_reason_code = None
    membership.end_date = closing
    membership.version += 1
    db.flush()
    return membership


def is_effective(membership: SchoolMembership) -> bool:
    """§3.8. Only ACTIVE is effective — suspended and terminated are not, and
    neither waits for an invalidation event to say so."""
    return membership.status is MembershipStatus.ACTIVE
