"""M07 §7.2: the read ports, and what they refuse to tell you.

These are the surface other modules resolve a subject basis through, so the
tests are as much about the *shape* of the answers as their correctness. Two
properties matter more than any individual lookup:

* a payer basis and a guardian basis are **different types**, not one record
  with a flag. §3.7 and M05 §3.2 point 9 both say a payer basis grants no
  attendance, document, health, profile or guardian right, and a flag is
  something a caller can forget to read. Forgetting it here hands a payer the
  child's records.
* nothing carries PII. §4 says "bez PII", and a port that leaked a name would
  do so silently — every caller would keep working, and the disclosure would
  be invisible until someone read the payload.
"""

from __future__ import annotations

import dataclasses
import uuid

from app.domains.family import guardian_commands as grd
from app.domains.family import payer_commands as pay
from app.domains.family import ports
from app.domains.family import primary_contact_commands as pgc
from app.domains.family import primary_payer_commands as ppd
from app.domains.family import service as fam
from app.domains.family.enums import (
    MemberKind,
    PayerBasisKind,
    RelationshipKind,
    VerificationMethod,
)
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipStatus, MembershipType
from app.domains.school.models import SchoolMembership
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school

ACTOR = "acc_staff"
APPROVER = "acc_approver"


def _rid() -> str:
    return str(uuid.uuid4())


class _Case:
    """A school where one adult is both the child's guardian and its payer."""

    def __init__(self, db: Session, *, name: str = "Klub Soko") -> None:
        self.db = db
        self.school = make_school(db, name=name)
        self.adult = make_person(db, given="Milan", family="Petrović")
        self.child = make_person(db, given="Iva", family="Petrović")
        for person in (self.adult, self.child):
            ensure_person_profile(db, school=self.school, person=person)
        # ACTIVE, not the factory's DRAFT default. §2.3 lets a link be
        # *created* against any open membership — a school may prepare an
        # enrolment before it takes effect — while §12 and M03 §6.1 decide
        # whether it is *effective* now. These ports answer the second
        # question, so a fixture on DRAFT memberships would be testing a
        # state that grants nothing.
        self.guardian_membership = mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.adult.id,
            membership_type=MembershipType.GUARDIAN,
            status=MembershipStatus.ACTIVE,
        )
        self.child_membership = mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.child.id,
            membership_type=MembershipType.PARTICIPANT,
            status=MembershipStatus.ACTIVE,
        )
        db.commit()

        self.family = fam.create_family(
            db, school_id=self.school.id, actor_account_id=ACTOR, request_id=_rid()
        )
        for person, kind in (
            (self.adult, MemberKind.ADULT),
            (self.child, MemberKind.DEPENDENT),
        ):
            fam.add_family_member(
                db,
                school_id=self.school.id,
                family_id=self.family.id,
                person_id=person.id,
                member_kind=kind,
                actor_account_id=ACTOR,
                request_id=_rid(),
            )
        db.commit()

    def guardian_link(self):
        link = grd.request_guardian_child_link(
            self.db,
            school_id=self.school.id,
            guardian_person_id=self.adult.id,
            child_person_id=self.child.id,
            relationship_kind=RelationshipKind.PARENT,
            actor_account_id=ACTOR,
            request_id=_rid(),
        )
        grd.verify_and_activate_guardian_link(
            self.db,
            school_id=self.school.id,
            link_id=link.id,
            expected_version=link.version,
            verification_method=VerificationMethod.SCHOOL_RECORD,
            policy_version="M07-VERIFY-1.0",
            actor_account_id=APPROVER,
            request_id=_rid(),
        )
        self.db.commit()
        return link

    def payer_link(self, **kw):
        link = pay.request_payer_child_link(
            self.db,
            school_id=self.school.id,
            payer_person_id=kw.pop("payer_person_id", self.adult.id),
            child_person_id=self.child.id,
            family_id=self.family.id,
            basis_kind=PayerBasisKind.FAMILY_ADULT,
            actor_account_id=ACTOR,
            request_id=_rid(),
        )
        pay.verify_and_activate_payer_link(
            self.db,
            school_id=self.school.id,
            link_id=link.id,
            expected_version=link.version,
            verification_method=VerificationMethod.SCHOOL_RECORD,
            policy_version="M07-VERIFY-1.0",
            actor_account_id=APPROVER,
            request_id=_rid(),
        )
        self.db.commit()
        return link


# ---------------------------------------------------------------------------
# The shape of the answers (§4, §3.7)
# ---------------------------------------------------------------------------


def test_a_payer_basis_is_a_different_type_from_a_guardian_basis(
    db: Session,
) -> None:
    """The privacy rule expressed as a type rather than a flag.

    If these were one record with a `scope` field, a caller could read the
    fields it wanted and never look at the flag — and the flag is the only
    thing standing between a billing module and a child's attendance record.
    Here the guardian fields are simply absent from a payer answer.
    """
    case = _Case(db)
    case.guardian_link()
    case.payer_link()

    guardian = ports.guardian_subject_basis(
        db,
        school_id=case.school.id,
        guardian_person_id=case.adult.id,
        child_person_id=case.child.id,
    )
    payer = ports.payer_subject_basis(
        db,
        school_id=case.school.id,
        payer_person_id=case.adult.id,
        child_person_id=case.child.id,
    )
    assert guardian is not None and payer is not None
    assert type(guardian) is not type(payer)
    assert payer.scope == ports.FINANCE_ONLY

    payer_fields = {f.name for f in dataclasses.fields(payer)}
    assert not any("guardian" in name for name in payer_fields)


def test_no_port_returns_a_name_or_any_other_pii(db: Session) -> None:
    """§4: "bez PII". A leak here would be silent — every caller would keep
    working and nobody would notice until someone read a payload."""
    case = _Case(db)
    case.guardian_link()
    case.payer_link()
    forbidden = {
        case.adult.given_name,
        case.adult.family_name,
        case.adult.display_name,
        case.child.given_name,
        case.child.display_name,
    }

    answers: list[object] = [
        ports.guardian_subject_basis(
            db,
            school_id=case.school.id,
            guardian_person_id=case.adult.id,
            child_person_id=case.child.id,
        ),
        ports.payer_subject_basis(
            db,
            school_id=case.school.id,
            payer_person_id=case.adult.id,
            child_person_id=case.child.id,
        ),
        ports.primary_guardian_contact(
            db, school_id=case.school.id, child_person_id=case.child.id
        ),
        ports.eligible_payers_for_billing(
            db, school_id=case.school.id, child_person_id=case.child.id
        ),
    ]
    rendered = repr(answers)
    for value in forbidden:
        assert value not in rendered


def test_a_basis_carries_the_versions_a_pre_commit_recheck_needs(
    db: Session,
) -> None:
    """§3.11: a high-risk write re-checks immediately before commit.

    The membership versions travel with the answer so that re-check is a
    comparison rather than another round trip, and so a stale basis is
    detectable rather than merely unlikely.
    """
    case = _Case(db)
    link = case.guardian_link()
    basis = ports.guardian_subject_basis(
        db,
        school_id=case.school.id,
        guardian_person_id=case.adult.id,
        child_person_id=case.child.id,
    )
    assert basis is not None
    assert basis.link_id == link.id
    assert basis.link_version == link.version
    assert basis.guardian_membership_version == case.guardian_membership.version
    assert basis.child_membership_version == case.child_membership.version


# ---------------------------------------------------------------------------
# When there is no basis
# ---------------------------------------------------------------------------


def test_a_pending_link_is_not_a_basis(db: Session) -> None:
    """Only ACTIVE counts. A request nobody has approved grants nothing, which
    is §1.2's whole point."""
    case = _Case(db)
    grd.request_guardian_child_link(
        db,
        school_id=case.school.id,
        guardian_person_id=case.adult.id,
        child_person_id=case.child.id,
        relationship_kind=RelationshipKind.PARENT,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()

    assert (
        ports.guardian_subject_basis(
            db,
            school_id=case.school.id,
            guardian_person_id=case.adult.id,
            child_person_id=case.child.id,
        )
        is None
    )


def test_a_revoked_link_stops_being_a_basis_immediately(db: Session) -> None:
    case = _Case(db)
    link = case.guardian_link()
    grd.revoke_guardian_link(
        db,
        school_id=case.school.id,
        link_id=link.id,
        expected_version=link.version,
        reason_code="GUARDIANSHIP_ENDED",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert (
        ports.guardian_subject_basis(
            db,
            school_id=case.school.id,
            guardian_person_id=case.adult.id,
            child_person_id=case.child.id,
        )
        is None
    )


def test_another_schools_link_is_not_a_basis_here(db: Session) -> None:
    case = _Case(db, name="Klub Soko")
    other = _Case(db, name="Klub Lav")
    other.guardian_link()

    assert (
        ports.guardian_subject_basis(
            db,
            school_id=case.school.id,
            guardian_person_id=other.adult.id,
            child_person_id=other.child.id,
        )
        is None
    )


def test_a_terminated_membership_removes_the_basis_without_waiting(
    db: Session,
) -> None:
    """§12: "Završetak M06 membership-a čini link neefektivnim odmah".

    The contract adds that an application consumer closes the link idempotently
    but the request-time resolver "ne čeka consumer" — so the basis has to
    disappear the moment the membership ends, not once something gets round to
    tidying up.

    Writing this test caught the port getting it wrong. The first version
    checked only whether the membership row *existed*, which can never fail:
    both link tables hold their memberships with `ON DELETE RESTRICT`, so a
    membership a link names cannot be deleted at all. The check was unreachable
    and the real case — a `TERMINATED` membership — sailed straight through as
    a valid basis.
    """
    case = _Case(db)
    case.guardian_link()
    assert (
        ports.guardian_subject_basis(
            db,
            school_id=case.school.id,
            guardian_person_id=case.adult.id,
            child_person_id=case.child.id,
        )
        is not None
    )

    membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.id == case.guardian_membership.id
        )
    ).scalar_one()
    membership.status = MembershipStatus.TERMINATED
    membership.termination_reason_code = "LEFT"
    membership.end_date = membership.start_date
    db.commit()

    assert (
        ports.guardian_subject_basis(
            db,
            school_id=case.school.id,
            guardian_person_id=case.adult.id,
            child_person_id=case.child.id,
        )
        is None
    )


def test_a_suspended_membership_also_stops_answering(db: Session) -> None:
    """Wider than §12 strictly requires, and deliberately so.

    §12 names termination. M03 §6.1 already treats current ACTIVE membership as
    the evidence any regular access needs, and a port that answered "basis
    exists" for a suspended member would hand that decision to whichever caller
    happened to look — which means it would be made differently in each one.
    Failing closed here keeps the answer in one place.
    """
    case = _Case(db)
    case.guardian_link()
    membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.id == case.guardian_membership.id
        )
    ).scalar_one()
    membership.status = MembershipStatus.SUSPENDED
    membership.suspension_reason_code = "UNPAID"
    db.commit()

    assert (
        ports.guardian_subject_basis(
            db,
            school_id=case.school.id,
            guardian_person_id=case.adult.id,
            child_person_id=case.child.id,
        )
        is None
    )


def test_a_terminated_payer_membership_removes_the_payer_basis(
    db: Session,
) -> None:
    """The same rule on the payer side, asserted rather than assumed."""
    case = _Case(db)
    case.payer_link()
    membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.id == case.guardian_membership.id
        )
    ).scalar_one()
    membership.status = MembershipStatus.TERMINATED
    membership.termination_reason_code = "LEFT"
    membership.end_date = membership.start_date
    db.commit()

    assert (
        ports.payer_subject_basis(
            db,
            school_id=case.school.id,
            payer_person_id=case.adult.id,
            child_person_id=case.child.id,
        )
        is None
    )


# ---------------------------------------------------------------------------
# Primary contact and billing
# ---------------------------------------------------------------------------


def test_no_primary_contact_is_a_real_answer(db: Session) -> None:
    """§3.1: zero is allowed, stale is not. A caller treating `None` as a
    failure has misread which of the two states is dangerous."""
    case = _Case(db)
    case.guardian_link()

    assert (
        ports.primary_guardian_contact(
            db, school_id=case.school.id, child_person_id=case.child.id
        )
        is None
    )


def test_the_primary_contact_disappears_with_its_link(db: Session) -> None:
    case = _Case(db)
    link = case.guardian_link()
    pgc.designate_primary_guardian_contact(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        guardian_child_link_id=link.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    assert (
        ports.primary_guardian_contact(
            db, school_id=case.school.id, child_person_id=case.child.id
        )
        == link.id
    )

    grd.revoke_guardian_link(
        db,
        school_id=case.school.id,
        link_id=link.id,
        expected_version=link.version,
        reason_code="GUARDIANSHIP_ENDED",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert (
        ports.primary_guardian_contact(
            db, school_id=case.school.id, child_person_id=case.child.id
        )
        is None
    )


def test_eligible_payers_lists_every_active_link_and_ranks_none(
    db: Session,
) -> None:
    """§3.9 and §2.5: M12 decides how an obligation splits, so the order here
    must mean nothing. Sorting by id is how you say that out loud — the
    primary payer is not first, and designating one does not reorder the list.
    """
    case = _Case(db)
    first = case.payer_link()

    second_person = make_person(db, given="Ana", family="Petrović")
    ensure_person_profile(db, school=case.school, person=second_person)
    mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=second_person.id,
        membership_type=MembershipType.CONTACT,
        status=MembershipStatus.ACTIVE,
    )
    db.commit()
    fam.add_family_member(
        db,
        school_id=case.school.id,
        family_id=case.family.id,
        person_id=second_person.id,
        member_kind=MemberKind.ADULT,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    second = case.payer_link(payer_person_id=second_person.id)

    ppd.designate_primary_payer(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        payer_child_link_id=second.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()

    listed = ports.eligible_payers_for_billing(
        db, school_id=case.school.id, child_person_id=case.child.id
    )
    assert set(listed) == {first.id, second.id}
    assert list(listed) == sorted(listed)


def test_a_revoked_payer_leaves_the_billing_list(db: Session) -> None:
    case = _Case(db)
    link = case.payer_link()
    pay.revoke_payer_link(
        db,
        school_id=case.school.id,
        link_id=link.id,
        expected_version=link.version,
        reason_code="ARRANGEMENT_ENDED",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert (
        ports.eligible_payers_for_billing(
            db, school_id=case.school.id, child_person_id=case.child.id
        )
        == ()
    )
