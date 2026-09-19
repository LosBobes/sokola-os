"""Ownership transitions: nominations, and the primary-owner term (M04 §3.4).

The rules here are the ones that keep a school from becoming unownable. Three
are worth reading before the code:

* **A school in preparation may have zero active owners** — but only while it
  holds one pending ``INITIAL_PRIMARY_OWNER`` nomination (§3.4.1). That is the
  precise version of "a school always has an owner", and the imprecise version
  is what makes provisioning either impossible or unsafe.
* **After the first acceptance, it may never have zero again** (§3.4.3, §3.4.5).
  The last active OWNER role cannot be revoked, and the role a live primary term
  points at cannot be removed before primacy is transferred.
* **A transfer is atomic and total** (§3.4.8): it closes one term and opens the
  next at the same instant, and changes no role set. The old owner stays an
  OWNER until a separate command says otherwise, because demoting them silently
  is how a transfer turns into a lockout.

What is *not* here: sending the M02 invitation, creating the M05 role, and the
step-up confirmation each command requires. Those modules do not exist yet
(finding F-12); this is the domain those commands will orchestrate, and the
guards below are enforced regardless of which caller eventually drives them.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode
from app.domains.identity.models import RoleAssignment
from app.domains.people.profile_models import SchoolPersonProfile
from app.domains.school.ownership_enums import (
    OwnerNominationCancelReason,
    OwnerNominationKind,
    OwnerNominationStatus,
    PrimaryOwnerTermReason,
)
from app.domains.school.ownership_models import (
    SchoolOwnerNomination,
    SchoolPrimaryOwnerTerm,
)
from app.platform import clock


def _lock_school(db: Session, school_id: str) -> None:
    """The same per-school lock the anchor takes.

    Ownership and status both serialize on the school row rather than on their
    own tables, so a transfer racing a deactivation cannot each hold a correct
    lock and still interleave.
    """
    db.execute(text("SELECT 1 FROM school WHERE id = :id FOR UPDATE"), {"id": school_id})


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def current_primary_term(db: Session, school_id: str) -> SchoolPrimaryOwnerTerm | None:
    return db.execute(
        select(SchoolPrimaryOwnerTerm).where(
            SchoolPrimaryOwnerTerm.school_id == school_id,
            SchoolPrimaryOwnerTerm.valid_to.is_(None),
        )
    ).scalar_one_or_none()


def active_owner_assignments(db: Session, school_id: str) -> list[RoleAssignment]:
    return list(
        db.execute(
            select(RoleAssignment).where(
                RoleAssignment.school_id == school_id,
                RoleAssignment.role_code == RoleCode.OWNER,
                RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
            )
        )
        .scalars()
        .all()
    )


def pending_initial_nomination(db: Session, school_id: str) -> SchoolOwnerNomination | None:
    return db.execute(
        select(SchoolOwnerNomination).where(
            SchoolOwnerNomination.school_id == school_id,
            SchoolOwnerNomination.kind == OwnerNominationKind.INITIAL_PRIMARY_OWNER,
            SchoolOwnerNomination.status == OwnerNominationStatus.PENDING,
        )
    ).scalar_one_or_none()


def _active_owner_assignment_for(
    db: Session, school_id: str, person_id: str
) -> RoleAssignment | None:
    return db.execute(
        select(RoleAssignment).where(
            RoleAssignment.school_id == school_id,
            RoleAssignment.person_id == person_id,
            RoleAssignment.role_code == RoleCode.OWNER,
            RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# OWN-01 / OWN-02: nominations
# ---------------------------------------------------------------------------


def nominate_owner(
    db: Session,
    *,
    school_id: str,
    person_id: str,
    kind: OwnerNominationKind,
    actor_ref: str,
) -> SchoolOwnerNomination:
    """Record the intent. The M02 invitation that carries it is a separate step."""
    _lock_school(db, school_id)

    profile = db.execute(
        select(SchoolPersonProfile).where(
            SchoolPersonProfile.school_id == school_id,
            SchoolPersonProfile.person_id == person_id,
        )
    ).scalar_one_or_none()
    if profile is None:
        # Safe-not-found: the caller learns nothing about whether the person
        # exists somewhere else, only that this school does not know them.
        raise NotFoundError("Osoba nije poznata ovoj školi.")

    if kind is OwnerNominationKind.INITIAL_PRIMARY_OWNER:
        if current_primary_term(db, school_id) is not None:
            raise ConflictError("Škola već ima primarnog vlasnika.")
        if pending_initial_nomination(db, school_id) is not None:
            raise ConflictError("Već postoji nominacija za prvog vlasnika.")
    elif _active_owner_assignment_for(db, school_id, person_id) is not None:
        # §3.4: nominating someone who is already an owner is not a no-op, it is
        # a sign the caller believes something untrue about the school.
        raise ConflictError("Osoba je već vlasnik ove škole.")

    nomination = SchoolOwnerNomination(
        school_id=school_id,
        target_person_id=person_id,
        target_school_person_profile_id=profile.id,
        kind=kind,
        created_by_actor_ref=actor_ref,
    )
    db.add(nomination)
    db.flush()
    return nomination


def attach_invitation(
    db: Session, *, nomination: SchoolOwnerNomination, invitation_id: str
) -> SchoolOwnerNomination:
    """Point the nomination at the invitation now carrying it.

    Reissuing changes only this reference (§2.6). An expired invitation leaves
    the nomination ``PENDING`` on purpose: giving up on a person is
    :func:`cancel_nomination`, and it should have to be said out loud.
    """
    if nomination.status is not OwnerNominationStatus.PENDING:
        raise ConflictError("Nominacija više nije na čekanju.")
    nomination.latest_invitation_id = invitation_id
    nomination.version += 1
    db.flush()
    return nomination


def cancel_nomination(
    db: Session,
    *,
    nomination: SchoolOwnerNomination,
    reason: OwnerNominationCancelReason,
    expected_version: int | None = None,
) -> SchoolOwnerNomination:
    if nomination.status is not OwnerNominationStatus.PENDING:
        raise ConflictError("Nominacija je već zatvorena.")
    if expected_version is not None and expected_version != nomination.version:
        raise ConflictError("Nominacija je u međuvremenu izmenjena.")

    nomination.status = OwnerNominationStatus.CANCELLED
    nomination.cancelled_at = clock.now()
    nomination.cancellation_reason_code = reason
    nomination.version += 1
    db.flush()
    return nomination


# ---------------------------------------------------------------------------
# OWN-03: acceptance
# ---------------------------------------------------------------------------


def fulfill_nomination(
    db: Session,
    *,
    nomination: SchoolOwnerNomination,
    role_assignment: RoleAssignment,
    actor_ref: str,
) -> tuple[SchoolOwnerNomination, SchoolPrimaryOwnerTerm | None]:
    """Mark the nomination fulfilled, and create the first primary term if the
    school has none.

    §8.1 OWN-03: if an effective term already exists it is **not** changed. An
    additional owner accepting must not quietly take primacy from whoever holds
    it, and neither must a second initial acceptance arriving late.

    Returns the term only when this call created one.
    """
    if nomination.status is not OwnerNominationStatus.PENDING:
        raise ConflictError("Nominacija je već zatvorena.")
    if role_assignment.role_code is not RoleCode.OWNER:
        raise ConflictError("Dodela uloge nije OWNER.")
    if role_assignment.school_id != nomination.school_id:
        raise ConflictError("Dodela uloge pripada drugoj školi.")
    if role_assignment.person_id != nomination.target_person_id:
        raise ConflictError("Dodela uloge pripada drugoj osobi.")
    if role_assignment.status is not RoleAssignmentStatus.ACTIVE:
        raise ConflictError("Dodela uloge nije aktivna.")

    _lock_school(db, nomination.school_id)
    now = clock.now()

    nomination.status = OwnerNominationStatus.FULFILLED
    nomination.fulfilled_at = now
    nomination.fulfilled_role_assignment_id = role_assignment.id
    nomination.version += 1

    term = None
    if current_primary_term(db, nomination.school_id) is None:
        term = SchoolPrimaryOwnerTerm(
            school_id=nomination.school_id,
            owner_person_id=nomination.target_person_id,
            owner_role_assignment_id=role_assignment.id,
            valid_from=now,
            source_nomination_id=nomination.id,
            reason_code=PrimaryOwnerTermReason.INITIAL_OWNER_ACCEPTED,
            created_by_actor_ref=actor_ref,
            created_at=now,
        )
        db.add(term)
    db.flush()
    return nomination, term


# ---------------------------------------------------------------------------
# OWN-04: transfer of primacy
# ---------------------------------------------------------------------------


def transfer_primary_ownership(
    db: Session,
    *,
    school_id: str,
    to_person_id: str,
    reason: PrimaryOwnerTermReason,
    actor_ref: str,
    case_reference: str | None = None,
) -> SchoolPrimaryOwnerTerm:
    """Close the current term and open the successor's, at the same instant.

    The target must already hold an active OWNER role (§3.4.6): a transfer moves
    a designation, it does not grant access. Granting the role as a side effect
    would make "make them primary" a way to make someone an owner without the
    command that is supposed to do that.

    The role set is untouched (§3.4.8) — the outgoing owner stays an OWNER.
    """
    if reason is PrimaryOwnerTermReason.INITIAL_OWNER_ACCEPTED:
        raise ConflictError("Prenos ne može nositi razlog prvog prihvatanja.")
    if reason is PrimaryOwnerTermReason.PLATFORM_LEGAL_OVERRIDE and not case_reference:
        raise ConflictError("Platformski override zahteva broj predmeta.")

    _lock_school(db, school_id)
    current = current_primary_term(db, school_id)
    if current is None:
        raise ConflictError("Škola nema aktuelnog primarnog vlasnika.")
    if current.owner_person_id == to_person_id:
        raise ConflictError("Osoba je već primarni vlasnik.")

    target_role = _active_owner_assignment_for(db, school_id, to_person_id)
    if target_role is None:
        raise ConflictError("Primalac nema aktivnu OWNER ulogu u ovoj školi.")

    effective_at = clock.now()
    if effective_at <= current.valid_from:
        # Two transfers inside one clock tick. Nudging forward keeps
        # `valid_to > valid_from` without inventing a reordering.
        effective_at = current.valid_from + dt.timedelta(microseconds=1)
    current.valid_to = effective_at

    successor = SchoolPrimaryOwnerTerm(
        school_id=school_id,
        owner_person_id=to_person_id,
        owner_role_assignment_id=target_role.id,
        valid_from=effective_at,
        reason_code=reason,
        created_by_actor_ref=actor_ref,
        case_reference=case_reference,
        created_at=effective_at,
    )
    db.add(successor)
    db.flush()
    return successor


# ---------------------------------------------------------------------------
# §3.4.5: what may not be taken away
# ---------------------------------------------------------------------------


def ensure_owner_role_may_be_removed(
    db: Session, *, school_id: str, role_assignment: RoleAssignment
) -> None:
    """Refuse the two removals that would leave a school unownable.

    Called before revoking, suspending or ending an OWNER assignment. It is a
    guard rather than a cascade on purpose: the caller is told which of the two
    problems it has, because "transfer primacy first" and "this is the last
    owner" need different answers from whoever asked.
    """
    if role_assignment.role_code is not RoleCode.OWNER:
        return

    term = current_primary_term(db, school_id)
    if term is not None and term.owner_role_assignment_id == role_assignment.id:
        raise ConflictError(
            "Uloga primarnog vlasnika ne može se ukloniti pre prenosa primarnosti."
        )

    remaining = db.execute(
        select(func.count())
        .select_from(RoleAssignment)
        .where(
            RoleAssignment.school_id == school_id,
            RoleAssignment.role_code == RoleCode.OWNER,
            RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
            RoleAssignment.id != role_assignment.id,
        )
    ).scalar_one()
    if remaining == 0 and term is not None:
        # Before the first acceptance a school legitimately has no owner
        # (§3.4.1), so this only bites once one has existed.
        raise ConflictError("Škola ne može ostati bez aktivnog vlasnika.")


def primary_owner_history(db: Session, school_id: str) -> list[SchoolPrimaryOwnerTerm]:
    return list(
        db.execute(
            select(SchoolPrimaryOwnerTerm)
            .where(SchoolPrimaryOwnerTerm.school_id == school_id)
            .order_by(SchoolPrimaryOwnerTerm.valid_from)
        )
        .scalars()
        .all()
    )
