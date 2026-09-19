"""M07 §2.1, §2.2: family groupings and who is in them.

The rule worth protecting here is a *negative* one, and §3.1 states it
outright: a family grouping is not derived from a surname, an email, an address
or another table, and it grants nothing. Two adults in one family see nothing
of each other because of it. §3.2 goes further — two families that share a
child are still invisible to one another, which is the separated-household case
the contract treats as normal rather than exceptional.

So most of what follows checks that the tables *permit* arrangements a naive
schema would forbid — the same person in two families, two families holding the
same child — and that the few things §2.1–2.2 do constrain are constrained by
the database rather than by a service that can forget.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.domains.family.enums import (
    FamilyMembershipStatus,
    FamilyStatus,
    MemberKind,
)
from app.domains.family.models import Family, FamilyMembership
from app.domains.identity.models import Person
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipType
from app.domains.school.models import School, SchoolMembership
from app.platform import clock
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school


def _family(db: Session, school: School, **overrides: object) -> Family:
    fields: dict[str, object] = {
        "school_id": school.id,
        "status": FamilyStatus.ACTIVE,
        "created_by_account_id": "acc_staff",
    }
    fields.update(overrides)
    family = Family(**fields)
    db.add(family)
    return family


def _member(
    db: Session,
    *,
    family: Family,
    person: Person,
    school_membership: SchoolMembership,
    **overrides: object,
) -> FamilyMembership:
    fields: dict[str, object] = {
        "school_id": family.school_id,
        "family_id": family.id,
        "person_id": person.id,
        "school_membership_id": school_membership.id,
        "member_kind": MemberKind.DEPENDENT,
        "status": FamilyMembershipStatus.ACTIVE,
        "effective_from": clock.now().date(),
    }
    fields.update(overrides)
    row = FamilyMembership(**fields)
    db.add(row)
    return row


def _participant(db: Session, school: School, given: str) -> tuple[Person, SchoolMembership]:
    person = make_person(db, given=given, family="Petrović")
    ensure_person_profile(db, school=school, person=person)
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    db.commit()
    return person, membership


def _refused(db: Session, constraint: str) -> None:
    """Assert the pending rows are rejected **on `constraint`**.

    Naming the constraint matters for the same reason it did in the guardian
    link's tests: a row built to break one rule frequently breaks another on
    the way, and a bare "something was refused" would keep passing if the rule
    under test disappeared entirely.
    """
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert constraint in str(caught.value), (
        f"expected {constraint} to refuse this row, got: {caught.value}"
    )
    db.rollback()


# ---------------------------------------------------------------------------
# What §3.1–3.2 require the schema to *allow*
# ---------------------------------------------------------------------------


def test_one_person_may_belong_to_several_families_in_one_school(db: Session) -> None:
    """§2.2: separated households, which are ordinary rather than exceptional.

    A schema keyed on `(school_id, person_id)` would make this impossible and
    would look perfectly reasonable while doing it — right up to the first
    divorced couple the school has to record.
    """
    school = make_school(db)
    child, child_membership = _participant(db, school, "Iva")

    mothers_household = _family(db, school, display_label="Petrović — majka")
    fathers_household = _family(db, school, display_label="Petrović — otac")
    db.flush()
    _member(db, family=mothers_household, person=child, school_membership=child_membership)
    _member(db, family=fathers_household, person=child, school_membership=child_membership)
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(FamilyMembership)
            .where(FamilyMembership.person_id == child.id)
        ).scalar_one()
        == 2
    )


def test_an_ended_membership_frees_the_key_for_a_return(db: Session) -> None:
    """§5.2: ENDED is terminal and coming back is a new row.

    The unique index is partial so that leaving and returning is recordable.
    A total key would force a school to delete the record that someone left in
    order to record that they came back.
    """
    school = make_school(db)
    child, child_membership = _participant(db, school, "Iva")
    family = _family(db, school)
    db.flush()

    left = _member(
        db,
        family=family,
        person=child,
        school_membership=child_membership,
        status=FamilyMembershipStatus.ENDED,
        effective_until=clock.now().date(),
        end_reason_code="MOVED_OUT",
    )
    db.commit()
    returned = _member(db, family=family, person=child, school_membership=child_membership)
    db.commit()

    assert left.id != returned.id
    assert (
        db.execute(
            select(func.count())
            .select_from(FamilyMembership)
            .where(FamilyMembership.family_id == family.id)
        ).scalar_one()
        == 2
    )


def test_a_person_may_not_hold_two_open_places_in_one_family(db: Session) -> None:
    school = make_school(db)
    child, child_membership = _participant(db, school, "Iva")
    family = _family(db, school)
    db.flush()
    _member(db, family=family, person=child, school_membership=child_membership)
    db.commit()

    _member(db, family=family, person=child, school_membership=child_membership)
    _refused(db, "uq_family_membership_open")


# ---------------------------------------------------------------------------
# Tenant safety (§4)
# ---------------------------------------------------------------------------


def test_a_membership_may_not_reach_into_another_schools_family(db: Session) -> None:
    school = make_school(db, name="Klub Soko")
    other = make_school(db, name="Klub Lav")
    child, child_membership = _participant(db, school, "Iva")
    foreign_family = _family(db, other)
    db.flush()

    _member(
        db,
        family=foreign_family,
        person=child,
        school_membership=child_membership,
        school_id=school.id,
    )
    _refused(db, "fk_family_membership_family")


def test_person_id_cannot_disagree_with_the_membership_beside_it(db: Session) -> None:
    """Why `person_id` is inside the composite key rather than beside it.

    With a plain `(school_id, school_membership_id)` reference, `person_id`
    would be a copy — and a copy of the fact that decides *whose* household
    record this is. Naming the person in the key makes the two unable to
    disagree, rather than merely expected not to.
    """
    school = make_school(db)
    child, child_membership = _participant(db, school, "Iva")
    other_child, _ = _participant(db, school, "Marko")
    family = _family(db, school)
    db.flush()

    _member(
        db,
        family=family,
        person=other_child,
        school_membership=child_membership,
    )
    _refused(db, "fk_family_membership_school_membership")


def test_a_school_membership_in_a_family_cannot_simply_be_deleted(db: Session) -> None:
    """`ON DELETE RESTRICT`: M06 ends a membership with a status, not a delete,
    and a delete that quietly took the household record with it would be
    tidying away the school's own record of who it grouped together."""
    school = make_school(db)
    child, child_membership = _participant(db, school, "Iva")
    family = _family(db, school)
    db.flush()
    _member(db, family=family, person=child, school_membership=child_membership)
    db.commit()

    db.delete(
        db.execute(
            select(SchoolMembership).where(SchoolMembership.id == child_membership.id)
        ).scalar_one()
    )
    _refused(db, "fk_family_membership_school_membership")


def test_archiving_a_family_takes_its_memberships(db: Session) -> None:
    """The family-side key cascades, unlike the membership-side one.

    Different facts, so different answers: a `school_membership` is M06's
    record and M07 has no business deleting it, while a `family_membership`
    exists only as part of the family grouping and means nothing once the
    grouping is gone.
    """
    school = make_school(db)
    child, child_membership = _participant(db, school, "Iva")
    family = _family(db, school)
    db.flush()
    _member(db, family=family, person=child, school_membership=child_membership)
    db.commit()

    family_id = family.id
    db.delete(db.execute(select(Family).where(Family.id == family_id)).scalar_one())
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(FamilyMembership)
            .where(FamilyMembership.family_id == family_id)
        ).scalar_one()
        == 0
    )


# ---------------------------------------------------------------------------
# The conditional rules §2.1–2.2 put in the database
# ---------------------------------------------------------------------------


def test_an_archived_family_says_why(db: Session) -> None:
    school = make_school(db)
    _family(db, school, status=FamilyStatus.ARCHIVED)
    _refused(db, "ck_family_archive_reason")


def test_an_active_family_carries_no_archive_reason(db: Session) -> None:
    """The symmetric half. A row that is ACTIVE while holding an archive reason
    is one that was archived and quietly brought back, and §5.1 makes ARCHIVED
    terminal — a family that re-forms is a new id."""
    school = make_school(db)
    _family(db, school, archive_reason_code="MERGED")
    _refused(db, "ck_family_archive_reason")


def test_a_family_label_may_be_absent_but_not_empty(db: Session) -> None:
    """§2.1 sets the label at 1..100 characters and makes it optional. Absent
    and empty are different: a school that has not named a grouping still has
    the grouping, but an empty string is a label nobody can read."""
    school = make_school(db)
    _family(db, school, display_label=None)
    db.commit()

    _family(db, school, display_label="")
    _refused(db, "ck_family_display_label_length")


@pytest.mark.parametrize(
    ("overrides", "why", "constraint"),
    [
        (
            {
                "status": FamilyMembershipStatus.ENDED,
                "end_reason_code": "MOVED_OUT",
            },
            "ENDED without an end date",
            "ck_family_membership_effective_until",
        ),
        (
            {"effective_until": dt.date(2030, 1, 1)},
            "ACTIVE carrying an end date",
            "ck_family_membership_effective_until",
        ),
        (
            {
                "status": FamilyMembershipStatus.ENDED,
                "effective_until": dt.date(2030, 1, 1),
            },
            "ENDED without a reason",
            "ck_family_membership_end_reason",
        ),
        (
            {"end_reason_code": "MOVED_OUT"},
            "ACTIVE carrying an end reason",
            "ck_family_membership_end_reason",
        ),
        (
            {
                "status": FamilyMembershipStatus.ENDED,
                "end_reason_code": "MOVED_OUT",
                "effective_from": dt.date(2030, 6, 1),
                "effective_until": dt.date(2030, 1, 1),
            },
            "ended before it started",
            "ck_family_membership_period",
        ),
        (
            {"version": 0},
            "version below 1",
            "ck_family_membership_version",
        ),
    ],
)
def test_a_half_ended_membership_is_refused(
    db: Session, overrides: dict[str, object], why: str, constraint: str
) -> None:
    """§2.2's conditional fields, one case each and in both directions.

    An ENDED row with no date and an ACTIVE row carrying one are the same
    mistake seen from either side, and only the pair of them makes `status` and
    the dates say the same thing.
    """
    school = make_school(db)
    child, child_membership = _participant(db, school, "Iva")
    family = _family(db, school)
    db.flush()

    _member(
        db,
        family=family,
        person=child,
        school_membership=child_membership,
        **overrides,
    )
    _refused(db, constraint)
