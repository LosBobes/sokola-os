"""M07 §2.6, §2.7: who the school calls first, and who it bills by default.

Both tables are *ordering*, not authority. §3.8 says a primary contact "je samo
redosled službene komunikacije škole; ne daje dodatne child permissions", and
§3.9 says a primary payer "ne određuje procenat odgovornosti". A primary
contact sees exactly what their guardian link already let them see.

Two properties carry the weight here:

* **zero is a legitimate answer.** §3.1 says "primarni kontakt može privremeno
  biti nula, nikad stale" — when the primary guardian's link is revoked, the
  designation goes with it and the child has none until someone designates
  again. A schema that made primacy a column on the child would have had to
  invent a value for that gap.
* **they are history rows.** Replacing a primary writes a new row and
  supersedes the old one, so "who was primary when this happened" stays
  answerable. That is the one question an incident actually raises.
"""

from __future__ import annotations

import pytest
from app.domains.family.enums import (
    DesignationStatus,
    FamilyStatus,
    LinkStatus,
    PayerBasisKind,
    RelationshipKind,
)
from app.domains.family.models import (
    Family,
    GuardianChildLink,
    PayerChildLink,
    PrimaryGuardianContactDesignation,
    PrimaryPayerDesignation,
)
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipType
from app.platform import clock
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school


class _Case:
    """A school, one child, and two adults each with a guardian link to it.

    Two adults because that is what primacy is *for*: with one guardian there
    is nothing to order.
    """

    def __init__(self, db: Session, *, name: str = "Klub Soko") -> None:
        self.school = make_school(db, name=name)
        self.child = make_person(db, given="Iva", family="Petrović")
        ensure_person_profile(db, school=self.school, person=self.child)
        self.child_membership = mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.child.id,
            membership_type=MembershipType.PARTICIPANT,
        )
        self.family = Family(
            school_id=self.school.id,
            status=FamilyStatus.ACTIVE,
            created_by_account_id="acc_staff",
        )
        db.add(self.family)
        db.flush()

        self.mother_link = self._guardian(db, "Ana")
        self.father_link = self._guardian(db, "Milan")
        self.payer_link = PayerChildLink(
            school_id=self.school.id,
            payer_person_id=self.mother_link.guardian_person_id,
            child_person_id=self.child.id,
            payer_school_membership_id=self.mother_link.guardian_school_membership_id,
            child_school_membership_id=self.child_membership.id,
            payer_membership_type=MembershipType.GUARDIAN.value,
            child_membership_type=MembershipType.PARTICIPANT.value,
            family_id=self.family.id,
            basis_kind=PayerBasisKind.FAMILY_ADULT,
            status=LinkStatus.ACTIVE,
            activated_at=clock.now(),
            decision_by_account_id="acc_approver",
            requested_by_account_id="acc_requester",
            requested_at=clock.now(),
        )
        db.add(self.payer_link)
        db.commit()

    def _guardian(self, db: Session, given: str) -> GuardianChildLink:
        adult = make_person(db, given=given, family="Petrović")
        ensure_person_profile(db, school=self.school, person=adult)
        membership = mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=adult.id,
            membership_type=MembershipType.GUARDIAN,
        )
        link = GuardianChildLink(
            school_id=self.school.id,
            guardian_person_id=adult.id,
            child_person_id=self.child.id,
            guardian_school_membership_id=membership.id,
            child_school_membership_id=self.child_membership.id,
            guardian_membership_type=MembershipType.GUARDIAN.value,
            child_membership_type=MembershipType.PARTICIPANT.value,
            relationship_kind=RelationshipKind.PARENT,
            status=LinkStatus.ACTIVE,
            activated_at=clock.now(),
            decision_by_account_id="acc_approver",
            requested_by_account_id="acc_requester",
            requested_at=clock.now(),
        )
        db.add(link)
        db.flush()
        return link


def _contact(
    case: _Case, link: GuardianChildLink, **overrides: object
) -> PrimaryGuardianContactDesignation:
    fields: dict[str, object] = {
        "school_id": case.school.id,
        "child_person_id": case.child.id,
        "guardian_child_link_id": link.id,
        "status": DesignationStatus.ACTIVE,
        "designated_by_account_id": "acc_staff",
        "designated_at": clock.now(),
    }
    fields.update(overrides)
    return PrimaryGuardianContactDesignation(**fields)


def _refused(db: Session, row: object, constraint: str) -> None:
    db.add(row)
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert constraint in str(caught.value), (
        f"expected {constraint} to refuse this row, got: {caught.value}"
    )
    db.rollback()


# ---------------------------------------------------------------------------
# One primary at a time, and history kept (§2.6, §5.4)
# ---------------------------------------------------------------------------


def test_a_child_may_not_have_two_active_primary_contacts(db: Session) -> None:
    case = _Case(db)
    db.add(_contact(case, case.mother_link))
    db.commit()

    _refused(
        db, _contact(case, case.father_link), "uq_primary_guardian_contact_active"
    )


def test_replacing_a_primary_keeps_the_old_row(db: Session) -> None:
    """§5.4: the old row becomes SUPERSEDED, it is not rewritten.

    That is what keeps "who was primary when this happened" answerable six
    months later — the one question an incident actually raises, and the one an
    in-place update destroys.
    """
    case = _Case(db)
    first = _contact(case, case.mother_link)
    db.add(first)
    db.commit()

    first.status = DesignationStatus.SUPERSEDED
    first.ended_at = clock.now()
    first.end_reason_code = "REPLACED"
    second = _contact(case, case.father_link)
    db.add(second)
    db.commit()

    rows = (
        db.execute(
            select(PrimaryGuardianContactDesignation).where(
                PrimaryGuardianContactDesignation.child_person_id == case.child.id
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert {r.status for r in rows} == {
        DesignationStatus.SUPERSEDED,
        DesignationStatus.ACTIVE,
    }
    assert first.guardian_child_link_id == case.mother_link.id


def test_a_child_may_have_no_primary_contact(db: Session) -> None:
    """§3.1: "primarni kontakt može privremeno biti nula, nikad stale."

    Several superseded and revoked rows, no active one. A schema that put
    primacy on the child as a column would have had to invent a value for this
    gap, and the honest value — nobody — is exactly what a foreign key with
    NOT NULL cannot say.
    """
    case = _Case(db)
    for reason in ("REPLACED", "LINK_REVOKED"):
        db.add(
            _contact(
                case,
                case.mother_link,
                status=DesignationStatus.REVOKED,
                ended_at=clock.now(),
                end_reason_code=reason,
            )
        )
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(PrimaryGuardianContactDesignation)
            .where(PrimaryGuardianContactDesignation.status == DesignationStatus.ACTIVE)
        ).scalar_one()
        == 0
    )


def test_contact_and_payer_primacies_are_independent(db: Session) -> None:
    """Why these are two tables rather than one with a discriminator.

    A child has at most one primary contact *and* at most one primary payer,
    independently. In a shared table the unique index would have needed the
    kind inside it to say that — the discriminator earning nothing and costing
    a column.
    """
    case = _Case(db)
    db.add(_contact(case, case.mother_link))
    db.add(
        PrimaryPayerDesignation(
            school_id=case.school.id,
            child_person_id=case.child.id,
            payer_child_link_id=case.payer_link.id,
            status=DesignationStatus.ACTIVE,
            designated_by_account_id="acc_staff",
            designated_at=clock.now(),
        )
    )
    db.commit()

    assert (
        db.execute(
            select(func.count()).select_from(PrimaryGuardianContactDesignation)
        ).scalar_one()
        == 1
    )
    assert (
        db.execute(select(func.count()).select_from(PrimaryPayerDesignation)).scalar_one()
        == 1
    )


# ---------------------------------------------------------------------------
# The link must be this child's (§2.6)
# ---------------------------------------------------------------------------


def test_a_designation_may_not_name_another_childs_link(db: Session) -> None:
    """The reason `child_person_id` is inside the foreign key.

    Both children are in the same school and both links are valid, so nothing
    about this row looks wrong — it would designate the school's first call
    about one child to an adult verified only for another. The composite key
    makes it impossible rather than merely incorrect.
    """
    case = _Case(db)
    other_child = make_person(db, given="Marko", family="Jovanović")
    ensure_person_profile(db, school=case.school, person=other_child)
    other_membership = mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=other_child.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    other_link = GuardianChildLink(
        school_id=case.school.id,
        guardian_person_id=case.mother_link.guardian_person_id,
        child_person_id=other_child.id,
        guardian_school_membership_id=case.mother_link.guardian_school_membership_id,
        child_school_membership_id=other_membership.id,
        guardian_membership_type=MembershipType.GUARDIAN.value,
        child_membership_type=MembershipType.PARTICIPANT.value,
        relationship_kind=RelationshipKind.PARENT,
        status=LinkStatus.ACTIVE,
        activated_at=clock.now(),
        decision_by_account_id="acc_approver",
        requested_by_account_id="acc_requester",
        requested_at=clock.now(),
    )
    db.add(other_link)
    db.commit()

    _refused(
        db,
        _contact(case, other_link),
        "fk_primary_guardian_contact_link",
    )


def test_a_designation_may_not_reach_into_another_school(db: Session) -> None:
    case = _Case(db, name="Klub Soko")
    other = _Case(db, name="Klub Lav")

    _refused(
        db,
        _contact(case, other.mother_link),
        "fk_primary_guardian_contact_link",
    )


def test_deleting_a_link_takes_its_designation(db: Session) -> None:
    """`CASCADE` as a backstop. §3.10 already makes revoking a link and closing
    its designations one transaction; this is what happens if the link itself
    ever goes, because a designation pointing at nothing records nothing."""
    case = _Case(db)
    db.add(_contact(case, case.mother_link))
    db.commit()

    db.delete(
        db.execute(
            select(GuardianChildLink).where(
                GuardianChildLink.id == case.mother_link.id
            )
        ).scalar_one()
    )
    db.commit()

    assert (
        db.execute(
            select(func.count()).select_from(PrimaryGuardianContactDesignation)
        ).scalar_one()
        == 0
    )


# ---------------------------------------------------------------------------
# §2.6's conditional fields, on both tables
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "why", "constraint"),
    [
        (
            {"status": DesignationStatus.SUPERSEDED, "end_reason_code": "REPLACED"},
            "SUPERSEDED without an end time",
            "ck_primary_guardian_contact_ended_at",
        ),
        (
            {"status": DesignationStatus.REVOKED, "end_reason_code": "LINK_REVOKED"},
            "REVOKED without an end time",
            "ck_primary_guardian_contact_ended_at",
        ),
        (
            {"ended_at": None, "end_reason_code": "REPLACED"},
            "ACTIVE carrying an end reason",
            "ck_primary_guardian_contact_end_reason",
        ),
        (
            {
                "status": DesignationStatus.SUPERSEDED,
                "ended_at": "now",
            },
            "SUPERSEDED without a reason",
            "ck_primary_guardian_contact_end_reason",
        ),
        (
            {"version": 0},
            "version below 1",
            "ck_primary_guardian_contact_version",
        ),
    ],
)
def test_a_half_ended_designation_is_refused(
    db: Session, overrides: dict[str, object], why: str, constraint: str
) -> None:
    case = _Case(db)
    resolved = {
        key: (clock.now() if value == "now" else value)
        for key, value in overrides.items()
    }
    _refused(db, _contact(case, case.mother_link, **resolved), constraint)


def test_an_active_designation_carrying_an_end_time_is_refused(db: Session) -> None:
    """The symmetric half, stated on its own because it is the one a service
    gets wrong: a live designation that already says when it ended is one
    nobody can trust either half of."""
    case = _Case(db)
    _refused(
        db,
        _contact(case, case.mother_link, ended_at=clock.now()),
        "ck_primary_guardian_contact_ended_at",
    )


def test_the_payer_designation_carries_the_same_rules(db: Session) -> None:
    """§2.7: "Polja su ista kao §2.6". Asserted rather than assumed, because
    "same as above" is exactly where a second table quietly diverges."""
    case = _Case(db)
    _refused(
        db,
        PrimaryPayerDesignation(
            school_id=case.school.id,
            child_person_id=case.child.id,
            payer_child_link_id=case.payer_link.id,
            status=DesignationStatus.REVOKED,
            end_reason_code="LINK_REVOKED",
            designated_by_account_id="acc_staff",
            designated_at=clock.now(),
        ),
        "ck_primary_payer_ended_at",
    )
