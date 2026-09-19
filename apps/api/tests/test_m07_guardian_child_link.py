"""M07 §2.3: one school's verified link between an adult and a child.

The rule these tests protect is that **a guardian link is a school's
verification, not a fact about two people**. Everything else follows from it:
the link is tenant-scoped, two schools may reach different conclusions about
the same pair, and each decided status has to say when it was decided, by whom,
and — for a refusal — why.

They are written against the database rather than a service because there is no
service yet. That is deliberate: the table goes in alongside
`guardian_relationship` and `guardian_school_access` and nothing reads it until
the readers are moved domain by domain (F-31). What can be established now is
that the row shapes production will accept are exactly the ones §2.3 describes,
and these tests establish that by trying to insert the ones it must not.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.domains.family.enums import (
    CHILD_MEMBERSHIP_TYPE,
    GUARDIAN_MEMBERSHIP_TYPE,
    LinkStatus,
    RelationshipKind,
)
from app.domains.family.models import GuardianChildLink
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipType
from app.domains.school.models import School, SchoolMembership
from app.domains.tenancy.models import TenantSecurityState
from app.platform import clock
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school


class _Pair:
    """A school with one guardian and one child, each holding the membership
    type §2.3's foreign keys require."""

    def __init__(self, db: Session, *, name: str = "Klub Soko") -> None:
        self.school = make_school(db, name=name)
        self.guardian = make_person(db, given="Milan", family="Petrović")
        self.child = make_person(db, given="Iva", family="Petrović")
        ensure_person_profile(db, school=self.school, person=self.guardian)
        ensure_person_profile(db, school=self.school, person=self.child)
        self.guardian_membership = mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.guardian.id,
            membership_type=MembershipType.GUARDIAN,
        )
        self.child_membership = mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.child.id,
            membership_type=MembershipType.PARTICIPANT,
        )
        db.commit()


def _link(pair: _Pair, **overrides: object) -> GuardianChildLink:
    """A `PENDING_VERIFICATION` link, which is the only status that needs no
    decision fields. Every other status is built by overriding from here, so a
    test that forgets a required field fails on the constraint it is about."""
    fields: dict[str, object] = {
        "school_id": pair.school.id,
        "guardian_person_id": pair.guardian.id,
        "child_person_id": pair.child.id,
        "guardian_school_membership_id": pair.guardian_membership.id,
        "child_school_membership_id": pair.child_membership.id,
        "guardian_membership_type": GUARDIAN_MEMBERSHIP_TYPE,
        "child_membership_type": CHILD_MEMBERSHIP_TYPE,
        "relationship_kind": RelationshipKind.PARENT,
        "status": LinkStatus.PENDING_VERIFICATION,
        "requested_by_account_id": "acc_requester",
        "requested_at": clock.now(),
    }
    fields.update(overrides)
    return GuardianChildLink(**fields)


def _active(pair: _Pair, **overrides: object) -> GuardianChildLink:
    fields: dict[str, object] = {
        "status": LinkStatus.ACTIVE,
        "activated_at": clock.now(),
        "decision_by_account_id": "acc_approver",
    }
    fields.update(overrides)
    return _link(pair, **fields)


def _revoked(pair: _Pair, **overrides: object) -> GuardianChildLink:
    fields: dict[str, object] = {
        "status": LinkStatus.REVOKED,
        "revoked_at": clock.now(),
        "decision_by_account_id": "acc_approver",
        "decision_reason_code": "GUARDIANSHIP_ENDED",
    }
    fields.update(overrides)
    return _link(pair, **fields)


def _refused(db: Session, link: GuardianChildLink, constraint: str) -> None:
    """Assert the database rejects `link` **on `constraint`**, then leave the
    session usable.

    Naming the constraint is not pedantry. A row built to violate one rule
    routinely violates another as a side effect — making a guardian their own
    child also points the child-side foreign key at a GUARDIAN membership — and
    a test that only asserted "something was refused" would pass while the rule
    it claims to cover was missing entirely.

    The flush has to happen *inside* the raises block: the constraint fires
    when the row reaches Postgres, and a helper that flushed for itself would
    move the failure outside the assertion.
    """
    db.add(link)
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert constraint in str(caught.value), (
        f"expected {constraint} to refuse this row, got: {caught.value}"
    )
    db.rollback()


# ---------------------------------------------------------------------------
# The shape §2.3 asks for
# ---------------------------------------------------------------------------


def test_a_verified_link_can_be_recorded(db: Session) -> None:
    pair = _Pair(db)
    link = _active(pair)
    db.add(link)
    db.commit()

    stored = db.execute(
        select(GuardianChildLink).where(GuardianChildLink.id == link.id)
    ).scalar_one()
    assert stored.status is LinkStatus.ACTIVE
    assert stored.school_id == pair.school.id
    assert stored.version == 1


# ---------------------------------------------------------------------------
# Tenant scope: the defect F-31 names (§2.3, M07 §1.1)
# ---------------------------------------------------------------------------


def test_two_schools_each_hold_their_own_verification_of_the_same_pair(
    db: Session,
) -> None:
    """The whole reason this table is tenant-scoped.

    The repo's `guardian_relationship` asserts `UNIQUE (guardian_person_id,
    child_person_id)` across the entire platform, so once school A records a
    relationship school B cannot record its own. Whether this adult may act for
    this child is a school's verification, and two schools checking the same
    family independently is the normal case, not a conflict.
    """
    first = _Pair(db, name="Klub Soko")

    second_school = make_school(db, name="Klub Lav")
    ensure_person_profile(db, school=second_school, person=first.guardian)
    ensure_person_profile(db, school=second_school, person=first.child)
    second_guardian_membership = mem.create_membership(
        db,
        school_id=second_school.id,
        person_id=first.guardian.id,
        membership_type=MembershipType.GUARDIAN,
    )
    second_child_membership = mem.create_membership(
        db,
        school_id=second_school.id,
        person_id=first.child.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    db.commit()

    db.add(_active(first))
    db.add(
        GuardianChildLink(
            school_id=second_school.id,
            guardian_person_id=first.guardian.id,
            child_person_id=first.child.id,
            guardian_school_membership_id=second_guardian_membership.id,
            child_school_membership_id=second_child_membership.id,
            guardian_membership_type=GUARDIAN_MEMBERSHIP_TYPE,
            child_membership_type=CHILD_MEMBERSHIP_TYPE,
            relationship_kind=RelationshipKind.PARENT,
            # The second school has not finished its own check, and is not
            # bound by the first school's conclusion.
            status=LinkStatus.PENDING_VERIFICATION,
            requested_by_account_id="acc_requester",
            requested_at=clock.now(),
        )
    )
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(GuardianChildLink)
            .where(
                GuardianChildLink.guardian_person_id == first.guardian.id,
                GuardianChildLink.child_person_id == first.child.id,
            )
        ).scalar_one()
        == 2
    )


def test_one_school_may_not_hold_two_open_links_for_a_pair(db: Session) -> None:
    pair = _Pair(db)
    db.add(_active(pair))
    db.commit()

    _refused(db, _link(pair), "uq_guardian_child_link_open")


def test_a_revoked_link_frees_the_key_for_a_fresh_check(db: Session) -> None:
    """§5.3: a revoked link is terminal and a new check is a new row.

    The unique index is partial for exactly this. If it covered every status,
    the history of a revocation would make the family permanently unable to be
    re-verified — and a school that has to delete the record of a revocation to
    approve a new link has no audit trail left.
    """
    pair = _Pair(db)
    revoked = _revoked(pair)
    db.add(revoked)
    db.commit()

    fresh = _active(pair)
    db.add(fresh)
    db.commit()

    assert fresh.id != revoked.id
    statuses = set(
        db.execute(
            select(GuardianChildLink.status).where(
                GuardianChildLink.school_id == pair.school.id
            )
        )
        .scalars()
        .all()
    )
    assert statuses == {LinkStatus.REVOKED, LinkStatus.ACTIVE}


def test_several_revoked_links_may_coexist(db: Session) -> None:
    pair = _Pair(db)
    db.add(_revoked(pair))
    db.commit()
    db.add(_revoked(pair, decision_reason_code="SCHOOL_DECISION"))
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(GuardianChildLink)
            .where(GuardianChildLink.school_id == pair.school.id)
        ).scalar_one()
        == 2
    )


# ---------------------------------------------------------------------------
# The type-pinned foreign keys (§2.3)
# ---------------------------------------------------------------------------


def test_a_guardian_link_may_not_name_a_staff_membership(db: Session) -> None:
    """Why the membership *type* is in the key rather than just the tenant.

    A coach who is also a parent holds two memberships in the same school. With
    only `(school_id, id)` in the key, a guardian link could name their STAFF
    membership and the database would see nothing wrong — the row would claim
    guardianship on the strength of an employment record.
    """
    pair = _Pair(db)
    staff = mem.create_membership(
        db,
        school_id=pair.school.id,
        person_id=pair.guardian.id,
        membership_type=MembershipType.STAFF,
    )
    db.commit()

    _refused(
        db,
        _link(pair, guardian_school_membership_id=staff.id),
        "fk_guardian_child_link_guardian_membership",
    )


def test_the_child_side_may_not_name_a_guardian_membership(db: Session) -> None:
    pair = _Pair(db)
    _refused(
        db,
        _link(pair, child_school_membership_id=pair.guardian_membership.id),
        "fk_guardian_child_link_child_membership",
    )


def test_the_denormalized_types_cannot_be_bent_to_fit(db: Session) -> None:
    """The CHECKs are what stop the type columns being used as an escape hatch.

    Without them, naming a STAFF membership would only need the row to also
    claim `guardian_membership_type = 'STAFF'` — the composite key would be
    satisfied and the type would have stopped meaning anything.
    """
    pair = _Pair(db)
    staff = mem.create_membership(
        db,
        school_id=pair.school.id,
        person_id=pair.guardian.id,
        membership_type=MembershipType.STAFF,
    )
    db.commit()

    _refused(
        db,
        _link(
            pair,
            guardian_school_membership_id=staff.id,
            guardian_membership_type="STAFF",
        ),
        "ck_guardian_child_link_guardian_type",
    )


def test_a_link_may_not_reach_into_another_school(db: Session) -> None:
    """§2.3's tenant-safe keys. The membership belongs to another school, so
    naming it from this school's link is impossible rather than merely wrong."""
    pair = _Pair(db, name="Klub Soko")
    other = _Pair(db, name="Klub Lav")

    _refused(
        db,
        _link(pair, child_school_membership_id=other.child_membership.id),
        "fk_guardian_child_link_child_membership",
    )


# ---------------------------------------------------------------------------
# The row-level rules §2.3 puts in the database
# ---------------------------------------------------------------------------


def test_nobody_is_their_own_guardian(db: Session) -> None:
    """§2.3: "ne sme biti isti ID".

    The adult here holds a PARTICIPANT membership of their own — an adult who
    also trains at the school, which M06 §3.2 allows — so both foreign keys
    are satisfied and the *only* thing standing between this row and the
    database is the distinct-people CHECK. Pointing the child side at the
    guardian's GUARDIAN membership instead would have been refused by the
    foreign key, and the CHECK could have been missing without anyone noticing.
    """
    pair = _Pair(db)
    own_participation = mem.create_membership(
        db,
        school_id=pair.school.id,
        person_id=pair.guardian.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    db.commit()

    _refused(
        db,
        _link(
            pair,
            child_person_id=pair.guardian.id,
            child_school_membership_id=own_participation.id,
        ),
        "ck_guardian_child_link_distinct_people",
    )


@pytest.mark.parametrize(
    ("overrides", "why", "constraint"),
    [
        (
            {"status": LinkStatus.ACTIVE, "decision_by_account_id": "acc_approver"},
            "ACTIVE without activated_at",
            "ck_guardian_child_link_activated_at",
        ),
        (
            {"activated_at": dt.datetime.now(dt.UTC)},
            "PENDING_VERIFICATION with activated_at",
            "ck_guardian_child_link_activated_at",
        ),
        (
            {
                "status": LinkStatus.REJECTED,
                "decision_by_account_id": "acc_approver",
                "decision_reason_code": "NO_EVIDENCE",
            },
            "REJECTED without rejected_at",
            "ck_guardian_child_link_rejected_at",
        ),
        (
            {
                "status": LinkStatus.REVOKED,
                "decision_by_account_id": "acc_approver",
                "decision_reason_code": "GUARDIANSHIP_ENDED",
            },
            "REVOKED without revoked_at",
            "ck_guardian_child_link_revoked_at",
        ),
        (
            {"status": LinkStatus.ACTIVE, "activated_at": dt.datetime.now(dt.UTC)},
            "ACTIVE with no decider named",
            "ck_guardian_child_link_decider",
        ),
        (
            {"decision_by_account_id": "acc_approver"},
            "PENDING_VERIFICATION with a decider already named",
            "ck_guardian_child_link_decider",
        ),
        (
            {
                "status": LinkStatus.REJECTED,
                "rejected_at": dt.datetime.now(dt.UTC),
                "decision_by_account_id": "acc_approver",
            },
            "REJECTED without a reason",
            "ck_guardian_child_link_decision_reason",
        ),
        (
            {
                "status": LinkStatus.ACTIVE,
                "activated_at": dt.datetime.now(dt.UTC),
                "decision_by_account_id": "acc_approver",
                "decision_reason_code": "WHY",
            },
            "ACTIVE carrying a refusal reason",
            "ck_guardian_child_link_decision_reason",
        ),
        ({"version": 0}, "version below 1",
            "ck_guardian_child_link_version"),
    ],
)
def test_a_half_decided_link_is_refused(
    db: Session, overrides: dict[str, object], why: str, constraint: str
) -> None:
    """§2.3's conditional fields, one case each.

    A decision nobody signed and a refusal with no reason are the two shapes
    that make a guardian link unauditable afterwards, which is the whole point
    of recording one. They are CHECK constraints rather than service code
    because a service is one forgotten branch away from writing them.
    """
    pair = _Pair(db)
    _refused(db, _link(pair, **overrides), constraint)


# ---------------------------------------------------------------------------
# What happens to a link when something it names goes away
# ---------------------------------------------------------------------------


def test_deleting_a_school_takes_its_links(db: Session) -> None:
    """`ON DELETE CASCADE` on `school_id`, for the case that should never arise.

    A school is never deleted in production — M04 deactivates it — and the
    database agrees: M03's `tenant_security_state` and `session_tenant_context`
    both hold a school in place with `ON DELETE RESTRICT`, and TEN-05 gives
    every school a security state at provisioning. So the row below has to be
    cleared first for the delete to proceed at all, and that is the honest
    shape of this test: it establishes what this table does when a school is
    genuinely removed, without pretending that removal is a path anyone walks.
    """
    pair = _Pair(db)
    db.add(_active(pair))
    db.commit()

    school_id = pair.school.id
    db.execute(
        delete(TenantSecurityState).where(TenantSecurityState.school_id == school_id)
    )
    db.delete(db.execute(select(School).where(School.id == school_id)).scalar_one())
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(GuardianChildLink)
            .where(GuardianChildLink.school_id == school_id)
        ).scalar_one()
        == 0
    )


def test_a_membership_named_by_a_link_cannot_simply_be_deleted(db: Session) -> None:
    """`ON DELETE RESTRICT`, deliberately.

    Cascading here would delete the school's record that it verified this
    guardian, as a side effect of tidying up a membership. A membership that
    should end has a `TERMINATED` status for saying so; deleting the row is not
    how M06 ends one, and the link is evidence.
    """
    pair = _Pair(db)
    db.add(_active(pair))
    db.commit()

    membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.id == pair.child_membership.id
        )
    ).scalar_one()
    db.delete(membership)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ---------------------------------------------------------------------------
# The rule a row cannot test, only a move between rows (§5.3)
# ---------------------------------------------------------------------------


def test_an_activated_link_keeps_its_start_time_after_revocation(
    db: Session,
) -> None:
    """§5.3 allows `ACTIVE -> REVOKED`, and the timestamp survives it.

    This constraint began life as `(status = 'ACTIVE') = (activated_at IS NOT
    NULL)`, which reads correctly and made the transition impossible: the only
    way past it was to null `activated_at` and erase the record of when
    guardianship began — at exactly the moment that record matters most.

    Every test in this file passed anyway, because they all built rows one
    status at a time and each satisfied the biconditional. A constraint over
    `status` cannot be validated by rows; it needs a move between them.
    """
    pair = _Pair(db)
    link = _active(pair)
    db.add(link)
    db.commit()
    started_at = link.activated_at

    link.status = LinkStatus.REVOKED
    link.revoked_at = clock.now()
    link.decision_reason_code = "GUARDIANSHIP_ENDED"
    db.commit()

    assert link.activated_at == started_at


def test_a_link_that_was_never_active_may_not_claim_a_start_time(
    db: Session,
) -> None:
    """The half of the old rule that was right, kept. A REJECTED link never
    granted anything, so a start time on one would be a fiction."""
    pair = _Pair(db)
    _refused(
        db,
        _link(
            pair,
            status=LinkStatus.REJECTED,
            rejected_at=clock.now(),
            activated_at=clock.now(),
            decision_by_account_id="acc_approver",
            decision_reason_code="NO_EVIDENCE",
        ),
        "ck_guardian_child_link_activated_at",
    )
