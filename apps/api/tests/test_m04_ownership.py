"""M04 §2.6–2.7, §3.4: who answers for a school.

The guarantees under test are the ones that decide whether a school can become
unownable. Several of them are asserted twice — once through the service, once
straight against the database — because the second is what still holds when a
future import, fixture or command forgets the first.
"""

from __future__ import annotations

import pytest
from app.common.errors import ConflictError, NotFoundError
from app.common.ids import new_id
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode
from app.domains.identity.models import RoleAssignment
from app.domains.school import ownership
from app.domains.school.ownership_enums import (
    OwnerNominationCancelReason,
    OwnerNominationKind,
    OwnerNominationStatus,
    PrimaryOwnerTermReason,
)
from app.domains.school.ownership_models import SchoolPrimaryOwnerTerm
from app.platform import clock
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import add_membership, assign_role, make_person, make_school


def _member(db: Session, school, *, given: str, role: RoleCode | None = None):
    """A person who belongs to the school, optionally with a role."""
    person = make_person(db, given=given, family="Vlasnik")
    add_membership(db, person=person, school=school)
    assignment = (
        assign_role(db, person=person, school=school, role=role) if role else None
    )
    return person, assignment


# ---------------------------------------------------------------------------
# Nominations (§2.6, §3.4.1)
# ---------------------------------------------------------------------------


def test_an_initial_nomination_is_the_only_thing_that_excuses_having_no_owner(
    db: Session,
) -> None:
    """§3.4.1 in one assertion: a school in preparation may sit at zero active
    owners, but only while exactly one pending initial nomination stands for it."""
    school = make_school(db)
    person, _ = _member(db, school, given="Prva")

    assert ownership.active_owner_assignments(db, school.id) == []
    assert ownership.current_primary_term(db, school.id) is None

    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.flush()

    assert nomination.status is OwnerNominationStatus.PENDING
    assert ownership.pending_initial_nomination(db, school.id) is nomination


def test_a_school_cannot_hold_two_pending_initial_nominations(db: Session) -> None:
    school = make_school(db)
    first, _ = _member(db, school, given="Prva")
    second, _ = _member(db, school, given="Druga")

    ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=first.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.flush()

    with pytest.raises(ConflictError, match="prvog vlasnika"):
        ownership.nominate_owner(
            db,
            school_id=school.id,
            person_id=second.id,
            kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
            actor_ref="platform",
        )


def test_the_database_refuses_a_second_pending_initial_nomination(db: Session) -> None:
    school = make_school(db)
    person, _ = _member(db, school, given="Prva")
    other, _ = _member(db, school, given="Druga")
    ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.commit()

    profile_id = db.execute(
        text("SELECT id FROM school_person_profile WHERE school_id = :s AND person_id = :p"),
        {"s": school.id, "p": other.id},
    ).scalar_one()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_owner_nomination (id, school_id, target_person_id, "
                "target_school_person_profile_id, kind, status, created_by_actor_ref, "
                "version, created_at, updated_at) VALUES (:id, :s, :p, :prof, "
                "'INITIAL_PRIMARY_OWNER', 'PENDING', 'x', 1, now(), now())"
            ),
            {"id": new_id("nom"), "s": school.id, "p": other.id, "prof": profile_id},
        )
    db.rollback()


def test_a_nomination_cannot_point_at_another_schools_profile(db: Session) -> None:
    """The composite foreign key, not a filter someone has to remember to write.

    It referenced `school_membership` before M06 landed and now references
    `school_person_profile` (finding F-14); the shape is identical, so this
    guarantee never lapsed.
    """
    left, right = make_school(db, name="Leva"), make_school(db, name="Desna")
    person, _ = _member(db, right, given="Tuđa")
    db.commit()

    foreign_profile = db.execute(
        text("SELECT id FROM school_person_profile WHERE school_id = :s"), {"s": right.id}
    ).scalar_one()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_owner_nomination (id, school_id, target_person_id, "
                "target_school_person_profile_id, kind, status, created_by_actor_ref, "
                "version, created_at, updated_at) VALUES (:id, :s, :p, :prof, "
                "'ADDITIONAL_OWNER', 'PENDING', 'x', 1, now(), now())"
            ),
            {"id": new_id("nom"), "s": left.id, "p": person.id, "prof": foreign_profile},
        )
    db.rollback()


def test_a_non_member_cannot_be_nominated(db: Session) -> None:
    school = make_school(db)
    outsider = make_person(db, given="Spoljni", family="Čovek")

    with pytest.raises(NotFoundError):
        ownership.nominate_owner(
            db,
            school_id=school.id,
            person_id=outsider.id,
            kind=OwnerNominationKind.ADDITIONAL_OWNER,
            actor_ref="owner",
        )


def test_an_existing_owner_is_not_nominated_again(db: Session) -> None:
    school = make_school(db)
    person, _ = _member(db, school, given="Vec", role=RoleCode.OWNER)

    with pytest.raises(ConflictError, match="već vlasnik"):
        ownership.nominate_owner(
            db,
            school_id=school.id,
            person_id=person.id,
            kind=OwnerNominationKind.ADDITIONAL_OWNER,
            actor_ref="owner",
        )


def test_reissuing_an_invitation_changes_only_the_reference(db: Session) -> None:
    """§2.6: an expired invitation does not kill the intent. Giving up on a
    person is a cancellation, and it has to be said out loud."""
    school = make_school(db)
    person, _ = _member(db, school, given="Ciljna")
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.ADDITIONAL_OWNER,
        actor_ref="owner",
    )
    db.flush()

    ownership.attach_invitation(db, nomination=nomination, invitation_id="inv_1")
    ownership.attach_invitation(db, nomination=nomination, invitation_id="inv_2")

    assert nomination.latest_invitation_id == "inv_2"
    assert nomination.target_person_id == person.id
    assert nomination.kind is OwnerNominationKind.ADDITIONAL_OWNER
    assert nomination.status is OwnerNominationStatus.PENDING
    assert nomination.version == 3


def test_cancelling_is_terminal_and_records_a_closed_reason(db: Session) -> None:
    school = make_school(db)
    person, _ = _member(db, school, given="Pogresna")
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.ADDITIONAL_OWNER,
        actor_ref="owner",
    )
    db.flush()

    ownership.cancel_nomination(
        db,
        nomination=nomination,
        reason=OwnerNominationCancelReason.WRONG_PERSON,
        expected_version=nomination.version,
    )
    assert nomination.status is OwnerNominationStatus.CANCELLED
    assert nomination.cancelled_at is not None

    with pytest.raises(ConflictError):
        ownership.cancel_nomination(
            db,
            nomination=nomination,
            reason=OwnerNominationCancelReason.REQUEST_WITHDRAWN,
        )


def test_a_stale_version_does_not_cancel(db: Session) -> None:
    school = make_school(db)
    person, _ = _member(db, school, given="Ciljna")
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.ADDITIONAL_OWNER,
        actor_ref="owner",
    )
    db.flush()
    ownership.attach_invitation(db, nomination=nomination, invitation_id="inv_1")

    with pytest.raises(ConflictError, match="izmenjena"):
        ownership.cancel_nomination(
            db,
            nomination=nomination,
            reason=OwnerNominationCancelReason.WRONG_PERSON,
            expected_version=1,
        )
    assert nomination.status is OwnerNominationStatus.PENDING


@pytest.mark.parametrize(
    "assignments",
    [
        "fulfilled_at = now(), fulfilled_role_assignment_id = NULL",
        "fulfilled_at = NULL, fulfilled_role_assignment_id = 'rol_x'",
        "fulfilled_at = NULL, fulfilled_role_assignment_id = NULL",
    ],
)
def test_fulfilled_must_carry_its_evidence(db: Session, assignments: str) -> None:
    """A nomination that says FULFILLED without naming both the moment and the
    role it produced is a claim with nothing behind it."""
    school = make_school(db)
    person, _ = _member(db, school, given="Ciljna")
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.ADDITIONAL_OWNER,
        actor_ref="owner",
    )
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                f"UPDATE school_owner_nomination SET status = 'FULFILLED', "
                f"{assignments} WHERE id = :id"
            ),
            {"id": nomination.id},
        )
    db.rollback()


# ---------------------------------------------------------------------------
# Acceptance (§8.1 OWN-03)
# ---------------------------------------------------------------------------


def _accept(db: Session, school, person, nomination):
    assignment = assign_role(db, person=person, school=school, role=RoleCode.OWNER)
    return ownership.fulfill_nomination(
        db, nomination=nomination, role_assignment=assignment, actor_ref="m02"
    )


def test_the_first_acceptance_creates_the_first_primary_term(db: Session) -> None:
    school = make_school(db)
    person, _ = _member(db, school, given="Prva")
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.flush()

    nomination, term = _accept(db, school, person, nomination)
    db.flush()

    assert nomination.status is OwnerNominationStatus.FULFILLED
    assert nomination.fulfilled_role_assignment_id is not None
    assert term is not None
    assert term.owner_person_id == person.id
    assert term.valid_to is None
    assert term.reason_code is PrimaryOwnerTermReason.INITIAL_OWNER_ACCEPTED
    assert term.source_nomination_id == nomination.id
    assert ownership.current_primary_term(db, school.id) is term


def test_an_additional_owner_accepting_does_not_take_primacy(db: Session) -> None:
    """§3.4.4 and OWN-03: the second owner gets the role, never the designation."""
    school = make_school(db)
    first, _ = _member(db, school, given="Prva")
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=first.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.flush()
    _, original_term = _accept(db, school, first, nomination)
    db.flush()

    second, _ = _member(db, school, given="Druga")
    extra = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=second.id,
        kind=OwnerNominationKind.ADDITIONAL_OWNER,
        actor_ref="owner",
    )
    db.flush()
    _, new_term = _accept(db, school, second, extra)
    db.flush()

    assert new_term is None
    assert ownership.current_primary_term(db, school.id) is original_term
    assert len(ownership.active_owner_assignments(db, school.id)) == 2


def test_acceptance_refuses_a_role_from_another_school_or_person(db: Session) -> None:
    school, other = make_school(db, name="Naša"), make_school(db, name="Tuđa")
    person, _ = _member(db, school, given="Ciljna")
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.ADDITIONAL_OWNER,
        actor_ref="owner",
    )
    db.flush()

    stranger, _ = _member(db, school, given="Neko")
    wrong_person = assign_role(db, person=stranger, school=school, role=RoleCode.OWNER)
    with pytest.raises(ConflictError, match="drugoj osobi"):
        ownership.fulfill_nomination(
            db, nomination=nomination, role_assignment=wrong_person, actor_ref="m02"
        )

    add_membership(db, person=person, school=other)
    wrong_school = assign_role(db, person=person, school=other, role=RoleCode.OWNER)
    with pytest.raises(ConflictError, match="drugoj školi"):
        ownership.fulfill_nomination(
            db, nomination=nomination, role_assignment=wrong_school, actor_ref="m02"
        )


def test_acceptance_refuses_a_role_that_is_not_owner(db: Session) -> None:
    school = make_school(db)
    person, _ = _member(db, school, given="Ciljna")
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.ADDITIONAL_OWNER,
        actor_ref="owner",
    )
    db.flush()
    manager = assign_role(db, person=person, school=school, role=RoleCode.MANAGER)

    with pytest.raises(ConflictError, match="nije OWNER"):
        ownership.fulfill_nomination(
            db, nomination=nomination, role_assignment=manager, actor_ref="m02"
        )


# ---------------------------------------------------------------------------
# Transfer (§3.4.6–3.4.9, §5.4)
# ---------------------------------------------------------------------------


def _school_with_primary(db: Session, name: str = "Klub Soko"):
    school = make_school(db, name=name)
    person, _ = _member(db, school, given="Prva")
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.flush()
    _, term = _accept(db, school, person, nomination)
    db.flush()
    assert term is not None
    return school, person, term


def test_a_transfer_closes_one_term_as_it_opens_the_next(db: Session) -> None:
    school, first, original = _school_with_primary(db)
    second, _ = _member(db, school, given="Druga", role=RoleCode.OWNER)

    successor = ownership.transfer_primary_ownership(
        db,
        school_id=school.id,
        to_person_id=second.id,
        reason=PrimaryOwnerTermReason.OWNER_TRANSFER,
        actor_ref=first.id,
    )
    db.flush()

    assert original.valid_to is not None
    assert original.valid_to == successor.valid_from
    assert successor.valid_to is None
    assert ownership.current_primary_term(db, school.id) is successor
    assert [t.owner_person_id for t in ownership.primary_owner_history(db, school.id)] == [
        first.id,
        second.id,
    ]


def test_a_transfer_changes_no_role_set(db: Session) -> None:
    """§3.4.8. The outgoing owner stays an OWNER; demoting them silently is how
    a transfer becomes a lockout."""
    school, first, _ = _school_with_primary(db)
    second, _ = _member(db, school, given="Druga", role=RoleCode.OWNER)

    ownership.transfer_primary_ownership(
        db,
        school_id=school.id,
        to_person_id=second.id,
        reason=PrimaryOwnerTermReason.OWNER_TRANSFER,
        actor_ref=first.id,
    )
    db.flush()

    owners = {a.person_id for a in ownership.active_owner_assignments(db, school.id)}
    assert owners == {first.id, second.id}


def test_a_transfer_target_must_already_be_an_owner(db: Session) -> None:
    """§3.4.6: the transfer moves a designation, it does not grant access."""
    school, first, _ = _school_with_primary(db)
    outsider, _ = _member(db, school, given="Bez")

    with pytest.raises(ConflictError, match="OWNER ulogu"):
        ownership.transfer_primary_ownership(
            db,
            school_id=school.id,
            to_person_id=outsider.id,
            reason=PrimaryOwnerTermReason.OWNER_TRANSFER,
            actor_ref=first.id,
        )


def test_transferring_to_the_current_primary_is_refused(db: Session) -> None:
    school, first, _ = _school_with_primary(db)
    with pytest.raises(ConflictError, match="već primarni"):
        ownership.transfer_primary_ownership(
            db,
            school_id=school.id,
            to_person_id=first.id,
            reason=PrimaryOwnerTermReason.OWNER_TRANSFER,
            actor_ref=first.id,
        )


def test_a_platform_override_must_name_its_case(db: Session) -> None:
    """§3.4.7: taking ownership away from someone leaves evidence behind."""
    school, first, _ = _school_with_primary(db)
    second, _ = _member(db, school, given="Druga", role=RoleCode.OWNER)

    with pytest.raises(ConflictError, match="predmeta"):
        ownership.transfer_primary_ownership(
            db,
            school_id=school.id,
            to_person_id=second.id,
            reason=PrimaryOwnerTermReason.PLATFORM_LEGAL_OVERRIDE,
            actor_ref="platform",
        )

    term = ownership.transfer_primary_ownership(
        db,
        school_id=school.id,
        to_person_id=second.id,
        reason=PrimaryOwnerTermReason.PLATFORM_LEGAL_OVERRIDE,
        actor_ref="platform",
        case_reference="CASE-2026-11",
    )
    db.flush()
    assert term.case_reference == "CASE-2026-11"
    assert term.created_by_actor_ref == "platform"


def test_the_database_refuses_an_override_without_a_case(db: Session) -> None:
    school, first, term = _school_with_primary(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE school_primary_owner_term SET reason_code = 'PLATFORM_LEGAL_OVERRIDE', "
                "case_reference = NULL WHERE id = :id"
            ),
            {"id": term.id},
        )
    db.rollback()


def test_the_database_refuses_two_open_terms(db: Session) -> None:
    school, first, _ = _school_with_primary(db)
    second, assignment = _member(db, school, given="Druga", role=RoleCode.OWNER)
    db.commit()
    assert assignment is not None

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_primary_owner_term (id, school_id, owner_person_id, "
                "owner_role_assignment_id, owner_role_code, valid_from, reason_code, "
                "created_by_actor_ref, created_at) "
                "VALUES (:id, :s, :p, :r, 'OWNER', now(), 'OWNER_TRANSFER', 'x', now())"
            ),
            {"id": new_id("pot"), "s": school.id, "p": second.id, "r": assignment.id},
        )
    db.rollback()


def test_a_term_cannot_point_at_a_non_owner_assignment(db: Session) -> None:
    """The composite FK includes role_code, so the same person's MANAGER
    assignment is not accepted as ownership proof."""
    school = make_school(db)
    person, _ = _member(db, school, given="Ciljna")
    manager = assign_role(db, person=person, school=school, role=RoleCode.MANAGER)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_primary_owner_term (id, school_id, owner_person_id, "
                "owner_role_assignment_id, owner_role_code, valid_from, reason_code, "
                "created_by_actor_ref, created_at) "
                "VALUES (:id, :s, :p, :r, 'OWNER', now(), 'OWNER_TRANSFER', 'x', now())"
            ),
            {"id": new_id("pot"), "s": school.id, "p": person.id, "r": manager.id},
        )
    db.rollback()


def test_two_transfers_inside_one_clock_tick_still_order(db: Session) -> None:
    school, first, _ = _school_with_primary(db)
    second, _ = _member(db, school, given="Druga", role=RoleCode.OWNER)
    third, _ = _member(db, school, given="Treca", role=RoleCode.OWNER)

    with clock.frozen_at("2026-04-01T09:00:00+00:00"):
        ownership.transfer_primary_ownership(
            db,
            school_id=school.id,
            to_person_id=second.id,
            reason=PrimaryOwnerTermReason.OWNER_TRANSFER,
            actor_ref=first.id,
        )
        db.flush()
        ownership.transfer_primary_ownership(
            db,
            school_id=school.id,
            to_person_id=third.id,
            reason=PrimaryOwnerTermReason.OWNER_TRANSFER,
            actor_ref=second.id,
        )
        db.flush()

    history = ownership.primary_owner_history(db, school.id)
    assert [t.owner_person_id for t in history] == [first.id, second.id, third.id]
    # Every closed interval is still non-empty, and they still meet exactly.
    for earlier, later in zip(history, history[1:], strict=False):
        assert earlier.valid_to is not None
        assert earlier.valid_to > earlier.valid_from
        assert earlier.valid_to == later.valid_from


# ---------------------------------------------------------------------------
# What may not be taken away (§3.4.5)
# ---------------------------------------------------------------------------


def test_the_primary_owners_role_cannot_be_removed_before_transfer(db: Session) -> None:
    school, first, term = _school_with_primary(db)
    _member(db, school, given="Druga", role=RoleCode.OWNER)
    assignment = db.get(RoleAssignment, term.owner_role_assignment_id)
    assert assignment is not None

    with pytest.raises(ConflictError, match="prenosa primarnosti"):
        ownership.ensure_owner_role_may_be_removed(
            db, school_id=school.id, role_assignment=assignment
        )


def test_the_two_rules_together_make_zero_owners_unreachable(db: Session) -> None:
    """§3.4.5 has two clauses, and it is their composition that matters.

    An additional owner may always go. The primary's role may not go before
    primacy moves. So there is no order of removals that reaches zero — which is
    the guarantee, and it is stronger than either clause alone.
    """
    school, first, term = _school_with_primary(db)
    second, extra = _member(db, school, given="Druga", role=RoleCode.OWNER)
    assert extra is not None
    original = db.get(RoleAssignment, term.owner_role_assignment_id)
    assert original is not None

    # The additional owner may go: someone else still owns the school.
    ownership.ensure_owner_role_may_be_removed(db, school_id=school.id, role_assignment=extra)
    # The primary's may not, whoever else exists.
    with pytest.raises(ConflictError, match="prenosa primarnosti"):
        ownership.ensure_owner_role_may_be_removed(
            db, school_id=school.id, role_assignment=original
        )

    # After a transfer the roles swap places, and so does the answer.
    ownership.transfer_primary_ownership(
        db,
        school_id=school.id,
        to_person_id=second.id,
        reason=PrimaryOwnerTermReason.OWNER_TRANSFER,
        actor_ref=first.id,
    )
    db.flush()
    ownership.ensure_owner_role_may_be_removed(db, school_id=school.id, role_assignment=original)
    with pytest.raises(ConflictError, match="prenosa primarnosti"):
        ownership.ensure_owner_role_may_be_removed(
            db, school_id=school.id, role_assignment=extra
        )


def test_the_last_owner_rule_still_catches_an_already_broken_school(db: Session) -> None:
    """Defence in depth. The clause above makes this state unreachable through
    the guard, so the only way here is past it — a direct revoke, an import, a
    fixture. It is exactly then that the second clause has to hold."""
    school, first, term = _school_with_primary(db)
    second, extra = _member(db, school, given="Druga", role=RoleCode.OWNER)
    assert extra is not None

    # Revoke the primary's role behind the guard's back.
    original = db.get(RoleAssignment, term.owner_role_assignment_id)
    assert original is not None
    original.status = RoleAssignmentStatus.REVOKED
    db.flush()

    with pytest.raises(ConflictError, match="bez aktivnog vlasnika"):
        ownership.ensure_owner_role_may_be_removed(
            db, school_id=school.id, role_assignment=extra
        )


def test_a_non_owner_role_is_never_blocked(db: Session) -> None:
    school, _, _ = _school_with_primary(db)
    person, manager = _member(db, school, given="Menadzer", role=RoleCode.MANAGER)
    assert manager is not None
    ownership.ensure_owner_role_may_be_removed(db, school_id=school.id, role_assignment=manager)


def test_a_school_before_its_first_owner_is_not_protected(db: Session) -> None:
    """§3.4.1 again, from the other side: the protection starts once an owner
    has existed, not before."""
    school = make_school(db)
    person, assignment = _member(db, school, given="Rana", role=RoleCode.OWNER)
    assert assignment is not None

    assert ownership.current_primary_term(db, school.id) is None
    ownership.ensure_owner_role_may_be_removed(
        db, school_id=school.id, role_assignment=assignment
    )


def test_a_term_survives_a_round_trip(db: Session) -> None:
    school, person, term = _school_with_primary(db)
    db.commit()
    db.expire_all()

    stored = db.get(SchoolPrimaryOwnerTerm, term.id)
    assert stored is not None
    assert stored.owner_role_code == "OWNER"
    assert stored.case_reference is None
    assert stored.reason_code is PrimaryOwnerTermReason.INITIAL_OWNER_ACCEPTED
