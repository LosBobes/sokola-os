"""M07 §7.1: the PAY commands — who pays, on what grounds, and nothing more.

The rule with no counterpart in the guardian group is §2.5 and §3.1's **basis**.
An adult in the child's own family is the ordinary case; a payer in family A
paying for a child in family B is refused unless the school ran the separate
sponsor process and recorded `SPONSOR_VERIFIED`. Checking that reads two
`family_membership` rows, so it is a service rule and could not be a
constraint.

The other thing these tests watch is what a payer link *does not* carry. §3.7
says it grants "samo M12 finansijskim operacijama", and M05 §3.2 point 9 that a
`PAYER` basis "nikad ne daje attendance/document/health/profile/guardian
pravo". No test here can prove a negative about future readers, but they do
establish that an ACTIVE payer link exists with no guardian link anywhere, and
that the events it emits say nothing about the relationship behind it.
"""

from __future__ import annotations

import uuid

import pytest
from app.common.errors import (
    ForbiddenError,
    InvalidRelationshipTransitionError,
    NotFoundError,
    RelationshipExistsError,
    StaleVersionError,
    ValidationFailedError,
)
from app.domains.family import payer_commands as pay
from app.domains.family import primary_payer_commands as ppd
from app.domains.family import service as fam
from app.domains.family.enums import (
    PAYER_LINK_ACTIVATED_EVENT,
    PAYER_LINK_REVOKED_EVENT,
    PRIMARY_PAYER_CHANGED_EVENT,
    DesignationStatus,
    LinkKind,
    LinkStatus,
    MemberKind,
    PayerBasisKind,
    VerificationMethod,
)
from app.domains.family.models import (
    GuardianChildLink,
    PayerChildLink,
    PrimaryPayerDesignation,
    RelationshipVerificationRecord,
)
from app.domains.identity.auth_models import UserAccount
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipType
from app.platform.outbox.models import OutboxMessage
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school

REQUESTER = "acc_requester"
APPROVER = "acc_approver"
POLICY = "M07-VERIFY-1.0"


def _rid() -> str:
    return str(uuid.uuid4())


class _Case:
    """A school, a child, an adult known only as a CONTACT, and a family with
    both of them in it."""

    def __init__(self, db: Session, *, name: str = "Klub Soko") -> None:
        self.db = db
        self.school = make_school(db, name=name)
        self.payer = make_person(db, given="Nikola", family="Jovanović")
        self.child = make_person(db, given="Iva", family="Petrović")
        for person in (self.payer, self.child):
            ensure_person_profile(db, school=self.school, person=person)
        mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.payer.id,
            membership_type=MembershipType.CONTACT,
        )
        mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.child.id,
            membership_type=MembershipType.PARTICIPANT,
        )
        db.commit()

        self.family = fam.create_family(
            db, school_id=self.school.id, actor_account_id=APPROVER, request_id=_rid()
        )
        for person, kind in (
            (self.payer, MemberKind.ADULT),
            (self.child, MemberKind.DEPENDENT),
        ):
            fam.add_family_member(
                db,
                school_id=self.school.id,
                family_id=self.family.id,
                person_id=person.id,
                member_kind=kind,
                actor_account_id=APPROVER,
                request_id=_rid(),
            )
        db.commit()

    def request(self, **kw):
        return pay.request_payer_child_link(
            self.db,
            school_id=self.school.id,
            payer_person_id=kw.pop("payer_person_id", self.payer.id),
            child_person_id=kw.pop("child_person_id", self.child.id),
            family_id=kw.pop("family_id", self.family.id),
            basis_kind=kw.pop("basis_kind", PayerBasisKind.FAMILY_ADULT),
            actor_account_id=kw.pop("actor_account_id", REQUESTER),
            request_id=kw.pop("request_id", _rid()),
            **kw,
        )

    def activate(self, link, **kw):
        return pay.verify_and_activate_payer_link(
            self.db,
            school_id=self.school.id,
            link_id=link.id,
            expected_version=kw.pop("expected_version", link.version),
            verification_method=kw.pop(
                "verification_method", VerificationMethod.SCHOOL_RECORD
            ),
            policy_version=POLICY,
            actor_account_id=kw.pop("actor_account_id", APPROVER),
            request_id=kw.pop("request_id", _rid()),
            **kw,
        )

    def active_link(self):
        link = self.request()
        self.activate(link)
        self.db.commit()
        return link


# ---------------------------------------------------------------------------
# §2.5 / §3.1: the basis
# ---------------------------------------------------------------------------


def test_an_adult_in_the_childs_family_may_pay(db: Session) -> None:
    case = _Case(db)
    link = case.active_link()

    assert link.status is LinkStatus.ACTIVE
    assert link.basis_kind is PayerBasisKind.FAMILY_ADULT
    assert link.payer_membership_type == MembershipType.CONTACT.value


def test_a_payer_outside_the_childs_family_is_refused(db: Session) -> None:
    """§3.1: "Payer je u Family A, dete samo u Family B" → 422.

    Both people exist, both hold the right membership types, and the family is
    real — everything a foreign key could check is satisfied. What is missing
    is the one thing only two `family_membership` reads can establish.
    """
    case = _Case(db)
    outsider = make_person(db, given="Petar", family="Ilić")
    ensure_person_profile(db, school=case.school, person=outsider)
    mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=outsider.id,
        membership_type=MembershipType.CONTACT,
    )
    db.commit()

    with pytest.raises(ValidationFailedError, match="Osnov za platioca"):
        case.request(payer_person_id=outsider.id)


def test_a_verified_sponsor_may_pay_from_outside_the_family(db: Session) -> None:
    """The single exception §3.1 allows, and it has to be stated in the row.

    A caller wanting to record a payer from outside the household says so with
    `SPONSOR_VERIFIED` rather than having it inferred from the absence of a
    membership — which is what keeps the ordinary case honest.
    """
    case = _Case(db)
    sponsor = make_person(db, given="Petar", family="Ilić")
    ensure_person_profile(db, school=case.school, person=sponsor)
    mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=sponsor.id,
        membership_type=MembershipType.CONTACT,
    )
    db.commit()

    link = case.request(
        payer_person_id=sponsor.id, basis_kind=PayerBasisKind.SPONSOR_VERIFIED
    )
    db.commit()
    assert link.status is LinkStatus.PENDING_VERIFICATION


def test_an_archived_family_takes_no_new_payer_links(db: Session) -> None:
    case = _Case(db)
    empty_family = fam.create_family(
        db, school_id=case.school.id, actor_account_id=APPROVER, request_id=_rid()
    )
    db.commit()
    fam.archive_family(
        db,
        school_id=case.school.id,
        family_id=empty_family.id,
        expected_version=1,
        reason_code="MERGED",
        actor_account_id=APPROVER,
        request_id=_rid(),
        has_open_obligations=lambda _s, _f: False,
    )
    db.commit()

    with pytest.raises(InvalidRelationshipTransitionError):
        case.request(
            family_id=empty_family.id, basis_kind=PayerBasisKind.SPONSOR_VERIFIED
        )


def test_a_staff_membership_cannot_stand_in_for_a_payer(db: Session) -> None:
    """§2.5 allows CONTACT or GUARDIAN and nothing else."""
    case = _Case(db)
    coach = make_person(db, given="Jelena", family="Trener")
    ensure_person_profile(db, school=case.school, person=coach)
    mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=coach.id,
        membership_type=MembershipType.STAFF,
    )
    db.commit()

    with pytest.raises(ValidationFailedError):
        case.request(payer_person_id=coach.id)


# ---------------------------------------------------------------------------
# §3.7: paying grants nothing
# ---------------------------------------------------------------------------


def test_an_active_payer_exists_with_no_guardian_link_anywhere(db: Session) -> None:
    """The separation the entity exists for, end to end through the commands.

    Before `PayerChildLink`, recording that someone pays for a child meant
    making them that child's guardian — which handed them attendance,
    documents, health and profile as a side effect of a billing arrangement.
    """
    case = _Case(db)
    case.active_link()

    assert (
        db.execute(select(func.count()).select_from(GuardianChildLink)).scalar_one()
        == 0
    )


def test_the_events_say_nothing_about_why_this_adult_pays(db: Session) -> None:
    """§4 / §7.3. `basis_kind` is the field that would carry it — "this adult
    pays because they are family" is a statement about the relationship."""
    case = _Case(db)
    case.active_link()

    event = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.event_type == PAYER_LINK_ACTIVATED_EVENT
        )
    ).scalar_one()
    assert event.payload["status"] == "ACTIVE"
    assert event.payload["version"] == 2
    assert "basis_kind" not in event.payload
    assert "family_id" not in event.payload
    assert "evidence_reference_digest" not in event.payload


# ---------------------------------------------------------------------------
# §3.5, §3.6, §5.3 — the same guarantees as the guardian group
# ---------------------------------------------------------------------------


def test_activation_writes_the_link_and_its_proof_together(db: Session) -> None:
    case = _Case(db)
    link = case.active_link()

    record = db.execute(select(RelationshipVerificationRecord)).scalar_one()
    assert record.link_kind is LinkKind.PAYER_CHILD
    assert record.payer_child_link_id == link.id
    assert record.guardian_child_link_id is None


def test_the_requester_may_not_approve_their_own_request(db: Session) -> None:
    case = _Case(db)
    link = case.request()
    db.commit()

    with pytest.raises(ForbiddenError):
        case.activate(link, actor_account_id=REQUESTER)


def test_a_payer_may_not_approve_their_own_link_through_another_account(
    db: Session,
) -> None:
    """§3.6, and the half no constraint can reach: the approving account is a
    different account, and belongs to the payer."""
    case = _Case(db)
    link = case.request()
    second_account = UserAccount(person_id=case.payer.id)
    db.add(second_account)
    db.commit()

    with pytest.raises(ForbiddenError):
        case.activate(link, actor_account_id=second_account.id)


def test_a_stale_version_blocks_activation(db: Session) -> None:
    case = _Case(db)
    link = case.request()
    db.commit()

    with pytest.raises(StaleVersionError):
        case.activate(link, expected_version=99)


def test_a_second_open_link_for_the_same_pair_is_refused(db: Session) -> None:
    case = _Case(db)
    case.active_link()

    with pytest.raises(RelationshipExistsError):
        case.request()


def test_several_payers_for_one_child_are_allowed(db: Session) -> None:
    """§2.5: "Više različitih ACTIVE payer-a je dozvoljeno". The refusal above
    is scoped to a pair, not to the child."""
    case = _Case(db)
    case.active_link()
    second = make_person(db, given="Ana", family="Jovanović")
    ensure_person_profile(db, school=case.school, person=second)
    mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=second.id,
        membership_type=MembershipType.CONTACT,
    )
    db.commit()
    fam.add_family_member(
        db,
        school_id=case.school.id,
        family_id=case.family.id,
        person_id=second.id,
        member_kind=MemberKind.ADULT,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    case.activate(case.request(payer_person_id=second.id))
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(PayerChildLink)
            .where(
                PayerChildLink.child_person_id == case.child.id,
                PayerChildLink.status == LinkStatus.ACTIVE,
            )
        ).scalar_one()
        == 2
    )


def test_a_rejection_emits_no_event(db: Session) -> None:
    case = _Case(db)
    link = case.request()
    db.commit()
    pay.reject_payer_link(
        db,
        school_id=case.school.id,
        link_id=link.id,
        expected_version=link.version,
        reason_code="NO_BASIS",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert link.status is LinkStatus.REJECTED
    # §7.3 lists activation and revocation, not refusal. Nothing downstream
    # ever acted on a pending link, and an event announcing that a named adult
    # was refused as a named child's payer is a disclosure with no consumer.
    # The FAM commands in this test's setup emit nothing either, so the whole
    # outbox is the right thing to count.
    assert db.execute(select(func.count()).select_from(OutboxMessage)).scalar_one() == 0


# ---------------------------------------------------------------------------
# PAY-04 and the designations
# ---------------------------------------------------------------------------


def test_revoking_a_payer_link_closes_its_primary_designation(db: Session) -> None:
    case = _Case(db)
    link = case.active_link()
    designation = ppd.designate_primary_payer(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        payer_child_link_id=link.id,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

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

    assert link.status is LinkStatus.REVOKED
    assert link.activated_at is not None  # the fix from the GRD slice, here too
    assert designation.status is DesignationStatus.REVOKED
    assert designation.end_reason_code == "LINK_REVOKED"

    event = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.event_type == PAYER_LINK_REVOKED_EVENT
        )
    ).scalar_one()
    assert event.payload["closed_designations"] == 1


def test_revoking_one_payer_leaves_the_others_alone(db: Session) -> None:
    """§2.5: several payers per child, and M12 decides how an obligation is
    split. Ending one arrangement is not ending the rest."""
    case = _Case(db)
    first = case.active_link()
    second_person = make_person(db, given="Ana", family="Jovanović")
    ensure_person_profile(db, school=case.school, person=second_person)
    mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=second_person.id,
        membership_type=MembershipType.CONTACT,
    )
    db.commit()
    fam.add_family_member(
        db,
        school_id=case.school.id,
        family_id=case.family.id,
        person_id=second_person.id,
        member_kind=MemberKind.ADULT,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()
    second = case.request(payer_person_id=second_person.id)
    case.activate(second)
    db.commit()

    pay.revoke_payer_link(
        db,
        school_id=case.school.id,
        link_id=first.id,
        expected_version=first.version,
        reason_code="ARRANGEMENT_ENDED",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert first.status is LinkStatus.REVOKED
    assert second.status is LinkStatus.ACTIVE


def test_a_designation_requires_an_active_link(db: Session) -> None:
    case = _Case(db)
    link = case.request()
    db.commit()

    with pytest.raises(InvalidRelationshipTransitionError):
        ppd.designate_primary_payer(
            db,
            school_id=case.school.id,
            child_person_id=case.child.id,
            payer_child_link_id=link.id,
            actor_account_id=APPROVER,
            request_id=_rid(),
        )


def test_replacing_the_wrong_current_primary_payer_is_refused(db: Session) -> None:
    """§5.4's "expected current". For a billing default, the lost update means
    invoices going to the wrong adult with nothing in the record saying why."""
    case = _Case(db)
    link = case.active_link()
    ppd.designate_primary_payer(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        payer_child_link_id=link.id,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    with pytest.raises(RelationshipExistsError):
        ppd.designate_primary_payer(
            db,
            school_id=case.school.id,
            child_person_id=case.child.id,
            payer_child_link_id=link.id,
            actor_account_id=APPROVER,
            request_id=_rid(),
            expected_current_designation_id=None,
        )


def test_removing_the_primary_payer_leaves_the_payer_link_active(
    db: Session,
) -> None:
    """§2.7: "nobody is the default" and "nobody pays" are different states,
    and only the first is what this command produces."""
    case = _Case(db)
    link = case.active_link()
    designation = ppd.designate_primary_payer(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        payer_child_link_id=link.id,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    ppd.remove_primary_payer(
        db,
        school_id=case.school.id,
        designation_id=designation.id,
        expected_version=designation.version,
        reason_code="SCHOOL_DECISION",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert designation.status is DesignationStatus.REVOKED
    assert link.status is LinkStatus.ACTIVE
    assert (
        db.execute(
            select(func.count())
            .select_from(PrimaryPayerDesignation)
            .where(PrimaryPayerDesignation.status == DesignationStatus.ACTIVE)
        ).scalar_one()
        == 0
    )
    assert (
        db.execute(
            select(func.count())
            .select_from(OutboxMessage)
            .where(OutboxMessage.event_type == PRIMARY_PAYER_CHANGED_EVENT)
        ).scalar_one()
        == 2
    )


def test_a_child_may_have_a_primary_contact_and_a_primary_payer_at_once(
    db: Session,
) -> None:
    """Why §2.6 and §2.7 are two tables. The primacies are independent, so a
    shared table would have needed the kind inside its unique index."""
    case = _Case(db)
    link = case.active_link()
    ppd.designate_primary_payer(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        payer_child_link_id=link.id,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert (
        db.execute(
            select(func.count())
            .select_from(PrimaryPayerDesignation)
            .where(PrimaryPayerDesignation.status == DesignationStatus.ACTIVE)
        ).scalar_one()
        == 1
    )


def test_another_schools_payer_link_is_not_found(db: Session) -> None:
    case = _Case(db, name="Klub Soko")
    other = _Case(db, name="Klub Lav")
    foreign = other.active_link()

    with pytest.raises(NotFoundError):
        pay.revoke_payer_link(
            db,
            school_id=case.school.id,
            link_id=foreign.id,
            expected_version=foreign.version,
            reason_code="ARRANGEMENT_ENDED",
            actor_account_id=APPROVER,
            request_id=_rid(),
        )


def test_a_repeated_request_id_replays(db: Session) -> None:
    case = _Case(db)
    request_id = _rid()
    first = case.request(request_id=request_id)
    db.commit()
    second = case.request(request_id=request_id)
    db.commit()
    assert first.id == second.id
