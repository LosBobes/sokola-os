"""M06 §2.3, §5.1: membership episodes.

The rule these tests protect is that **a terminated membership is terminal and
coming back is a new row**. Reviving the row would overwrite when the person was
previously a member, and that history is the only reason a school can answer
"did this family leave and come back, or have they been with us throughout".

``is_first_activation`` is the visible consequence: derived once at activation
and then frozen, so a later episode never retroactively makes an earlier one
look like a return.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import ConflictError
from app.common.ids import new_id
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipStatus, MembershipType
from app.domains.school.models import SchoolMembership
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school

PARTICIPANT = MembershipType.PARTICIPANT
STAFF = MembershipType.STAFF


def _pair(db: Session, name: str = "Ana"):
    school, person = make_school(db), make_person(db, given=name)
    ensure_person_profile(db, school=school, person=person)
    return school, person


# ---------------------------------------------------------------------------
# Episodes (§2.3, §3.1)
# ---------------------------------------------------------------------------


def test_a_person_may_hold_several_membership_types_in_one_school(db: Session) -> None:
    """§3.2: a parent who also coaches is both. The old UNIQUE(school, person)
    made the second one impossible, which is why this migration dropped it."""
    school, person = _pair(db)
    guardian = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=MembershipType.GUARDIAN
    )
    staff = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=STAFF
    )
    db.commit()

    assert guardian.id != staff.id
    held = (
        db.execute(
            select(SchoolMembership.membership_type).where(
                SchoolMembership.school_id == school.id,
                SchoolMembership.person_id == person.id,
            )
        )
        .scalars()
        .all()
    )
    assert set(held) == {MembershipType.GUARDIAN, STAFF}


def test_a_second_open_episode_of_one_type_is_refused(db: Session) -> None:
    school, person = _pair(db)
    mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    db.flush()

    with pytest.raises(ConflictError, match="otvoreno članstvo"):
        mem.create_membership(
            db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
        )


def test_the_database_refuses_a_second_open_episode(db: Session) -> None:
    school, person = _pair(db)
    mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_membership (id, school_id, person_id, status, "
                "membership_type, start_date, is_first_activation, version, "
                "record_status, created_at, updated_at) VALUES (:id, :s, :p, 'DRAFT', "
                "'PARTICIPANT', current_date, false, 1, 'ACTIVE', now(), now())"
            ),
            {"id": new_id("mem"), "s": school.id, "p": person.id},
        )
    db.rollback()


def test_a_terminated_episode_frees_the_natural_key(db: Session) -> None:
    """Partial uniqueness: history must not lock someone out of rejoining."""
    school, person = _pair(db)
    first = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=PARTICIPANT,
        status=MembershipStatus.ACTIVE,
    )
    db.flush()
    mem.terminate_membership(db, first, reason_code="LEFT")
    db.flush()

    second = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=PARTICIPANT,
        status=MembershipStatus.ACTIVE,
    )
    db.commit()
    assert second.id != first.id
    assert first.status is MembershipStatus.TERMINATED


# ---------------------------------------------------------------------------
# is_first_activation (§2.3, §3.5)
# ---------------------------------------------------------------------------


def test_a_returning_member_is_not_a_first_activation(db: Session) -> None:
    """The whole reason a terminated row is never revived: this answer has to
    survive the person leaving and coming back."""
    school, person = _pair(db)
    first = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    mem.activate_membership(db, first)
    db.flush()
    assert first.is_first_activation is True

    mem.terminate_membership(db, first, reason_code="LEFT")
    db.flush()

    second = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    mem.activate_membership(db, second)
    db.commit()

    assert second.is_first_activation is False
    # And the first episode's answer was not rewritten by the second.
    assert first.is_first_activation is True


def test_resuming_from_suspension_does_not_re_answer_the_question(db: Session) -> None:
    """A suspension is the same episode continuing, not a new arrival."""
    school, person = _pair(db)
    membership = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    mem.activate_membership(db, membership)
    db.flush()
    assert membership.is_first_activation is True

    mem.suspend_membership(db, membership, reason_code="PAUSE")
    mem.activate_membership(db, membership)
    db.commit()
    assert membership.is_first_activation is True


def test_first_activation_is_per_membership_type(db: Session) -> None:
    """Being a guardian before says nothing about first becoming a participant."""
    school, person = _pair(db)
    guardian = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=MembershipType.GUARDIAN
    )
    mem.activate_membership(db, guardian)
    participant = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    mem.activate_membership(db, participant)
    db.commit()

    assert guardian.is_first_activation is True
    assert participant.is_first_activation is True


# ---------------------------------------------------------------------------
# Transitions (§5.1)
# ---------------------------------------------------------------------------


def test_a_draft_may_be_abandoned_without_pretending_it_was_real(db: Session) -> None:
    """§5.1 allows DRAFT → TERMINATED precisely so giving up before activation
    does not require first activating."""
    school, person = _pair(db)
    membership = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    db.flush()
    assert membership.status is MembershipStatus.DRAFT

    mem.terminate_membership(db, membership, reason_code="NEVER_STARTED")
    db.commit()
    assert membership.status is MembershipStatus.TERMINATED
    assert membership.is_first_activation is False


@pytest.mark.parametrize(
    ("from_status", "action"),
    [
        (MembershipStatus.TERMINATED, "activate"),
        (MembershipStatus.TERMINATED, "suspend"),
        (MembershipStatus.TERMINATED, "terminate"),
        (MembershipStatus.DRAFT, "suspend"),
        (MembershipStatus.ACTIVE, "activate"),
    ],
)
def test_a_forbidden_transition_is_refused(
    db: Session, from_status: MembershipStatus, action: str
) -> None:
    school, person = _pair(db)
    membership = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    if from_status is MembershipStatus.ACTIVE:
        mem.activate_membership(db, membership)
    elif from_status is MembershipStatus.TERMINATED:
        mem.terminate_membership(db, membership, reason_code="LEFT")
    db.flush()

    with pytest.raises(ConflictError, match="nije dozvoljen"):
        if action == "activate":
            mem.activate_membership(db, membership)
        elif action == "suspend":
            mem.suspend_membership(db, membership, reason_code="X")
        else:
            mem.terminate_membership(db, membership, reason_code="X")


def test_suspension_and_termination_each_require_a_reason(db: Session) -> None:
    school, person = _pair(db)
    membership = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    mem.activate_membership(db, membership)
    db.flush()

    with pytest.raises(ConflictError, match="razlog"):
        mem.suspend_membership(db, membership, reason_code="")
    with pytest.raises(ConflictError, match="razlog"):
        mem.terminate_membership(db, membership, reason_code="")


def test_only_active_is_effective(db: Session) -> None:
    """§3.8: suspended is immediately ineffective for M03/M05, and does not wait
    for an invalidation event to become so."""
    school, person = _pair(db)
    membership = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    assert not mem.is_effective(membership)  # DRAFT

    mem.activate_membership(db, membership)
    assert mem.is_effective(membership)

    mem.suspend_membership(db, membership, reason_code="PAUSE")
    assert not mem.is_effective(membership)

    mem.activate_membership(db, membership)
    mem.terminate_membership(db, membership, reason_code="LEFT")
    assert not mem.is_effective(membership)


# ---------------------------------------------------------------------------
# The §2.3 CHECK contracts
# ---------------------------------------------------------------------------


def test_a_suspended_row_must_carry_its_reason(db: Session) -> None:
    school, person = _pair(db)
    membership = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE school_membership SET status = 'SUSPENDED' WHERE id = :id"),
            {"id": membership.id},
        )
    db.rollback()


def test_a_terminated_row_must_carry_a_reason_and_an_end_date(db: Session) -> None:
    school, person = _pair(db)
    membership = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=PARTICIPANT
    )
    db.commit()

    for assignments in (
        "status = 'TERMINATED', end_date = current_date",
        "status = 'TERMINATED', termination_reason_code = 'X'",
    ):
        with pytest.raises(IntegrityError):
            db.execute(
                text(f"UPDATE school_membership SET {assignments} WHERE id = :id"),
                {"id": membership.id},
            )
        db.rollback()


def test_an_end_date_cannot_precede_the_start(db: Session) -> None:
    school, person = _pair(db)
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=PARTICIPANT,
        start_date=dt.date(2026, 6, 1),
    )
    db.flush()

    with pytest.raises(ConflictError, match="pre datuma početka"):
        mem.terminate_membership(
            db, membership, reason_code="LEFT", end_date=dt.date(2026, 5, 1)
        )
    db.rollback()


def test_the_database_refuses_an_end_date_before_the_start(db: Session) -> None:
    school, person = _pair(db)
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=PARTICIPANT,
        start_date=dt.date(2026, 6, 1),
    )
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE school_membership SET status = 'TERMINATED', "
                "termination_reason_code = 'X', end_date = '2026-05-01' WHERE id = :id"
            ),
            {"id": membership.id},
        )
    db.rollback()


def test_a_membership_carries_no_role(db: Session) -> None:
    """§2.3, stated as a test because the absence is the point: what someone may
    *do* is M05's question, and a role column here would be a second answer."""
    school, person = _pair(db)
    membership = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=STAFF
    )
    assert not hasattr(membership, "role")
    assert not hasattr(membership, "role_code")
