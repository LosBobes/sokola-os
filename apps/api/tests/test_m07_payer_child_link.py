"""M07 §2.5: an adult who pays for a child, and learns nothing by paying.

The point of this table is a *separation*, so the tests are mostly about what
the schema now makes possible rather than what it forbids. Until it existed,
the only way to record that someone pays for a child was to make them that
child's guardian — which handed them the child's attendance, documents, health
records and profile as a side effect of a billing arrangement. §3.7 and M05
§3.2 point 9 both forbid that, and neither can be honoured while the financial
link is inexpressible on its own.

None of these tests claim the separation is *enforced*. It is not, and cannot
be here: a table cannot stop a reader joining to it. What they establish is
that a payer link stands up with no guardian link anywhere in sight, which is
the precondition for M05 being able to resolve a `FINANCE_ONLY` basis at all.
"""

from __future__ import annotations

import pytest
from app.domains.family.enums import (
    FamilyStatus,
    LinkStatus,
    MemberKind,
    PayerBasisKind,
)
from app.domains.family.models import (
    Family,
    FamilyMembership,
    GuardianChildLink,
    PayerChildLink,
)
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipType
from app.domains.school.models import SchoolMembership
from app.platform import clock
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school


class _Case:
    """A school with a child, an adult who is only a `CONTACT`, and a family.

    The adult deliberately holds **no** GUARDIAN membership and no guardian
    link. That is the arrangement the repo could not express before this table:
    someone the school knows purely as a billing contact.
    """

    def __init__(self, db: Session, *, name: str = "Klub Soko") -> None:
        self.school = make_school(db, name=name)
        self.payer = make_person(db, given="Nikola", family="Jovanović")
        self.child = make_person(db, given="Iva", family="Petrović")
        ensure_person_profile(db, school=self.school, person=self.payer)
        ensure_person_profile(db, school=self.school, person=self.child)
        self.payer_membership = mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.payer.id,
            membership_type=MembershipType.CONTACT,
        )
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
        db.commit()


def _link(case: _Case, **overrides: object) -> PayerChildLink:
    fields: dict[str, object] = {
        "school_id": case.school.id,
        "payer_person_id": case.payer.id,
        "child_person_id": case.child.id,
        "payer_school_membership_id": case.payer_membership.id,
        "child_school_membership_id": case.child_membership.id,
        "payer_membership_type": MembershipType.CONTACT.value,
        "child_membership_type": MembershipType.PARTICIPANT.value,
        "family_id": case.family.id,
        "basis_kind": PayerBasisKind.FAMILY_ADULT,
        "status": LinkStatus.PENDING_VERIFICATION,
        "requested_by_account_id": "acc_requester",
        "requested_at": clock.now(),
    }
    fields.update(overrides)
    return PayerChildLink(**fields)


def _active(case: _Case, **overrides: object) -> PayerChildLink:
    fields: dict[str, object] = {
        "status": LinkStatus.ACTIVE,
        "activated_at": clock.now(),
        "decision_by_account_id": "acc_approver",
    }
    fields.update(overrides)
    return _link(case, **fields)


def _refused(db: Session, link: PayerChildLink, constraint: str) -> None:
    db.add(link)
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert constraint in str(caught.value), (
        f"expected {constraint} to refuse this row, got: {caught.value}"
    )
    db.rollback()


# ---------------------------------------------------------------------------
# The gap this table closes (F-32, §3.7)
# ---------------------------------------------------------------------------


def test_a_payer_needs_no_guardian_link_at_all(db: Session) -> None:
    """The whole reason the entity exists.

    Before this table, marking someone as paying for a child meant creating a
    guardian relationship, which carries attendance, documents, health and
    profile access with it. Here the adult holds a `CONTACT` membership, no
    GUARDIAN membership, and no guardian link — and the row stands.
    """
    case = _Case(db)
    db.add(_active(case))
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(GuardianChildLink)
            .where(GuardianChildLink.child_person_id == case.child.id)
        ).scalar_one()
        == 0
    )
    assert (
        db.execute(
            select(func.count())
            .select_from(SchoolMembership)
            .where(
                SchoolMembership.person_id == case.payer.id,
                SchoolMembership.membership_type == MembershipType.GUARDIAN,
            )
        ).scalar_one()
        == 0
    )
    stored = db.execute(select(PayerChildLink)).scalar_one()
    assert stored.status is LinkStatus.ACTIVE
    assert stored.basis_kind is PayerBasisKind.FAMILY_ADULT


def test_a_guardian_may_also_be_a_payer(db: Session) -> None:
    """§2.5 allows `GUARDIAN` on the payer side too — the ordinary case where
    the parent paying the fees is the same parent who collects the child.

    The two links stay separate rows because they are separate facts: revoking
    the financial arrangement must not revoke the guardianship, and §5.3 gives
    each its own lifecycle.
    """
    case = _Case(db)
    guardian_membership = mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=case.payer.id,
        membership_type=MembershipType.GUARDIAN,
    )
    db.commit()

    db.add(
        _active(
            case,
            payer_school_membership_id=guardian_membership.id,
            payer_membership_type=MembershipType.GUARDIAN.value,
        )
    )
    db.commit()

    assert db.execute(select(func.count()).select_from(PayerChildLink)).scalar_one() == 1


def test_several_active_payers_for_one_child_are_allowed(db: Session) -> None:
    """§2.5: "Više različitih ACTIVE payer-a je dozvoljeno; M12 određuje da li
    i kako se deli obaveza." Two separated parents each paying a share is the
    case, and a key on the child alone would make it unrecordable."""
    case = _Case(db)
    db.add(_active(case))

    second = make_person(db, given="Jelena", family="Jovanović")
    ensure_person_profile(db, school=case.school, person=second)
    second_membership = mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=second.id,
        membership_type=MembershipType.CONTACT,
    )
    db.commit()
    db.add(
        _active(
            case,
            payer_person_id=second.id,
            payer_school_membership_id=second_membership.id,
        )
    )
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(PayerChildLink)
            .where(PayerChildLink.child_person_id == case.child.id)
        ).scalar_one()
        == 2
    )


def test_one_payer_may_not_hold_two_open_links_for_a_child(db: Session) -> None:
    case = _Case(db)
    db.add(_active(case))
    db.commit()

    _refused(db, _link(case), "uq_payer_child_link_open")


# ---------------------------------------------------------------------------
# The type-pinned foreign keys (§2.5)
# ---------------------------------------------------------------------------


def test_a_payer_may_not_be_named_by_their_staff_membership(db: Session) -> None:
    """The CHECK and the foreign key each catch half of this.

    A coach who also pays for their own child holds a STAFF membership.
    Claiming it directly fails the CHECK, because STAFF is not one of §2.5's
    two allowed types; claiming it while *recording* the type as CONTACT fails
    the foreign key, because the membership's real type is STAFF. Both halves
    are needed — either alone leaves a way through.
    """
    case = _Case(db)
    staff = mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=case.payer.id,
        membership_type=MembershipType.STAFF,
    )
    db.commit()

    _refused(
        db,
        _link(
            case,
            payer_school_membership_id=staff.id,
            payer_membership_type=MembershipType.STAFF.value,
        ),
        "ck_payer_child_link_payer_type",
    )
    _refused(
        db,
        _link(case, payer_school_membership_id=staff.id),
        "fk_payer_child_link_payer_membership",
    )


def test_the_child_side_must_be_a_participant(db: Session) -> None:
    case = _Case(db)
    _refused(
        db,
        _link(case, child_school_membership_id=case.payer_membership.id),
        "fk_payer_child_link_child_membership",
    )


def test_a_link_may_not_reach_into_another_school(db: Session) -> None:
    case = _Case(db, name="Klub Soko")
    other = _Case(db, name="Klub Lav")

    _refused(
        db,
        _link(case, child_school_membership_id=other.child_membership.id),
        "fk_payer_child_link_child_membership",
    )
    _refused(db, _link(case, family_id=other.family.id), "fk_payer_child_link_family")


# ---------------------------------------------------------------------------
# What happens to a family that still has a payer on it (§3.13)
# ---------------------------------------------------------------------------


def test_a_family_with_an_open_payer_link_cannot_be_deleted(db: Session) -> None:
    """`RESTRICT`, unlike `family_membership`'s cascade.

    §3.13 makes an open link a *blocker* on archiving a family. A cascade here
    would let the database remove the evidence that the blocker exists, as a
    side effect of the very operation the blocker is meant to refuse.
    """
    case = _Case(db)
    db.add(_active(case))
    db.commit()

    db.delete(
        db.execute(select(Family).where(Family.id == case.family.id)).scalar_one()
    )
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert "fk_payer_child_link_family" in str(caught.value)
    db.rollback()


def test_a_family_membership_still_cascades(db: Session) -> None:
    """The contrast that makes the previous test meaningful: the two foreign
    keys to `family` answer differently because they are different facts."""
    case = _Case(db)
    member = FamilyMembership(
        school_id=case.school.id,
        family_id=case.family.id,
        person_id=case.child.id,
        school_membership_id=case.child_membership.id,
        member_kind=MemberKind.DEPENDENT,
        effective_from=clock.now().date(),
    )
    db.add(member)
    db.commit()

    family_id = case.family.id
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
# §2.5's conditional rules, "uslovno kao Guardian link"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "why", "constraint"),
    [
        (
            {"status": LinkStatus.ACTIVE, "decision_by_account_id": "acc_approver"},
            "ACTIVE without activated_at",
            "ck_payer_child_link_activated_at",
        ),
        (
            {
                "status": LinkStatus.REJECTED,
                "decision_by_account_id": "acc_approver",
                "decision_reason_code": "NO_BASIS",
            },
            "REJECTED without rejected_at",
            "ck_payer_child_link_rejected_at",
        ),
        (
            {
                "status": LinkStatus.REVOKED,
                "decision_by_account_id": "acc_approver",
                "decision_reason_code": "ARRANGEMENT_ENDED",
            },
            "REVOKED without revoked_at",
            "ck_payer_child_link_revoked_at",
        ),
        (
            {"status": LinkStatus.ACTIVE, "activated_at": clock.now()},
            "ACTIVE with no decider named",
            "ck_payer_child_link_decider",
        ),
        (
            {"decision_by_account_id": "acc_approver"},
            "PENDING_VERIFICATION with a decider already named",
            "ck_payer_child_link_decider",
        ),
        (
            {"decision_reason_code": "WHY"},
            "PENDING_VERIFICATION carrying a refusal reason",
            "ck_payer_child_link_decision_reason",
        ),
        ({"version": 0}, "version below 1", "ck_payer_child_link_version"),
    ],
)
def test_a_half_decided_payer_link_is_refused(
    db: Session, overrides: dict[str, object], why: str, constraint: str
) -> None:
    case = _Case(db)
    _refused(db, _link(case, **overrides), constraint)
