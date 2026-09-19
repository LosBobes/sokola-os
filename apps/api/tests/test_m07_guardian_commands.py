"""M07 §7.1: the GRD commands — proving guardianship and taking it away.

Three rules carry this group, and none of them could be a constraint.

**§5.3 / §3.6, the distinct approver.** The account that approves must differ
from the one that asked, *and* must not belong to either person in the link.
The second half is the one a database cannot reach: it needs M01 to say which
person an account belongs to, and a CHECK sees only ids. Without it, a guardian
with two accounts approves their own guardianship.

**§3.5, atomic activation.** ACTIVE and its single immutable verification
record appear together or not at all. A link active without its proof is a
guardianship nobody can account for afterwards.

**§3.10, revocation closes designations.** §3.1 permits a child to have *no*
primary contact and names a stale one as the thing that must never happen — so
the designations close in the same transaction, not in a consumer that may lag.
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
from app.domains.family import guardian_commands as grd
from app.domains.family import primary_contact_commands as pgc
from app.domains.family.enums import (
    GUARDIAN_LINK_ACTIVATED_EVENT,
    GUARDIAN_LINK_REVOKED_EVENT,
    PRIMARY_GUARDIAN_CHANGED_EVENT,
    DesignationStatus,
    LinkKind,
    LinkStatus,
    RelationshipKind,
    VerificationMethod,
)
from app.domains.family.models import (
    PrimaryGuardianContactDesignation,
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
    def __init__(self, db: Session, *, name: str = "Klub Soko") -> None:
        self.db = db
        self.school = make_school(db, name=name)
        self.guardian = make_person(db, given="Milan", family="Petrović")
        self.child = make_person(db, given="Iva", family="Petrović")
        for person in (self.guardian, self.child):
            ensure_person_profile(db, school=self.school, person=person)
        mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.guardian.id,
            membership_type=MembershipType.GUARDIAN,
        )
        mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.child.id,
            membership_type=MembershipType.PARTICIPANT,
        )
        db.commit()

    def request(self, **kw):
        return grd.request_guardian_child_link(
            self.db,
            school_id=self.school.id,
            guardian_person_id=kw.pop("guardian_person_id", self.guardian.id),
            child_person_id=kw.pop("child_person_id", self.child.id),
            relationship_kind=kw.pop("relationship_kind", RelationshipKind.PARENT),
            actor_account_id=kw.pop("actor_account_id", REQUESTER),
            request_id=kw.pop("request_id", _rid()),
            **kw,
        )

    def activate(self, link, **kw):
        return grd.verify_and_activate_guardian_link(
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
# GRD-01: a request is always PENDING
# ---------------------------------------------------------------------------


def test_a_request_never_lands_active(db: Session) -> None:
    """§1.2 forbids a parent activating another guardian themselves. The
    guarantee is structural: no path creates an ACTIVE link, because activation
    is a separate command needing a second account."""
    case = _Case(db)
    link = case.request()
    db.commit()

    assert link.status is LinkStatus.PENDING_VERIFICATION
    assert link.decision_by_account_id is None
    assert link.activated_at is None


def test_a_second_open_request_for_the_same_pair_is_refused(db: Session) -> None:
    case = _Case(db)
    case.request()
    db.commit()

    with pytest.raises(RelationshipExistsError):
        case.request()


def test_a_guardian_without_an_open_guardian_membership_is_refused(
    db: Session,
) -> None:
    """§6 `M07_MEMBERSHIP_TYPE_MISMATCH`. The composite foreign key would catch
    a wrong *type*, but only once the row is built; this refuses before that
    and with a message that says nothing about which person is the problem."""
    case = _Case(db)
    stranger = make_person(db, given="Nikola", family="Jovanović")
    ensure_person_profile(db, school=case.school, person=stranger)
    db.commit()

    with pytest.raises(ValidationFailedError):
        case.request(guardian_person_id=stranger.id)


def test_nobody_may_request_guardianship_of_themselves(db: Session) -> None:
    case = _Case(db)
    with pytest.raises(ValidationFailedError):
        case.request(child_person_id=case.guardian.id)


# ---------------------------------------------------------------------------
# GRD-02: §3.5 and §3.6
# ---------------------------------------------------------------------------


def test_activation_writes_the_link_and_its_proof_together(db: Session) -> None:
    case = _Case(db)
    link = case.request()
    db.commit()
    case.activate(link, verification_method=VerificationMethod.SIGNED_DECLARATION)
    db.commit()

    assert link.status is LinkStatus.ACTIVE
    assert link.activated_at is not None
    assert link.decision_by_account_id == APPROVER
    assert link.version == 2

    record = db.execute(select(RelationshipVerificationRecord)).scalar_one()
    assert record.guardian_child_link_id == link.id
    assert record.link_kind is LinkKind.GUARDIAN_CHILD
    assert record.verified_by_account_id == APPROVER
    assert record.policy_version == POLICY


def test_the_requester_may_not_approve_their_own_request(db: Session) -> None:
    """§5.3's distinct approver. One person twice is not two people."""
    case = _Case(db)
    link = case.request()
    db.commit()

    with pytest.raises(ForbiddenError):
        case.activate(link, actor_account_id=REQUESTER)


def test_a_guardian_may_not_approve_their_own_link_through_another_account(
    db: Session,
) -> None:
    """§3.6, and the half no constraint can reach.

    The approving account is a *different* account, so the distinct-approver
    check above passes. It belongs to the guardian named in the link, which
    only M01 can reveal — a CHECK sees two unequal ids and is satisfied.
    """
    case = _Case(db)
    link = case.request()
    second_account = UserAccount(person_id=case.guardian.id)
    db.add(second_account)
    db.commit()

    with pytest.raises(ForbiddenError):
        case.activate(link, actor_account_id=second_account.id)


def test_an_unrelated_account_may_approve(db: Session) -> None:
    """The control for the two refusals above: the rule is about *whose*
    account it is, not about accounts in general."""
    case = _Case(db)
    link = case.request()
    staff = make_person(db, given="Jelena", family="Staff")
    staff_account = UserAccount(person_id=staff.id)
    db.add(staff_account)
    db.commit()

    case.activate(link, actor_account_id=staff_account.id)
    db.commit()
    assert link.status is LinkStatus.ACTIVE


def test_only_a_pending_link_activates(db: Session) -> None:
    case = _Case(db)
    link = case.active_link()

    with pytest.raises(InvalidRelationshipTransitionError):
        case.activate(link, expected_version=link.version)


def test_a_stale_version_blocks_activation(db: Session) -> None:
    case = _Case(db)
    link = case.request()
    db.commit()

    with pytest.raises(StaleVersionError):
        case.activate(link, expected_version=99)


def test_activation_emits_one_event_carrying_no_relationship_detail(
    db: Session,
) -> None:
    """§7.3 / §4: opaque IDs, status, version, reason code.

    `relationship_kind` is deliberately absent. "X is the legal guardian of Y"
    is exactly the sentence §4 keeps out of events, and it would be the only
    field in the payload that carries it.
    """
    case = _Case(db)
    case.active_link()

    events = (
        db.execute(
            select(OutboxMessage).where(
                OutboxMessage.event_type == GUARDIAN_LINK_ACTIVATED_EVENT
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["status"] == "ACTIVE"
    assert payload["version"] == 2
    assert "relationship_kind" not in payload
    assert "evidence_reference_digest" not in payload


# ---------------------------------------------------------------------------
# GRD-03 / GRD-04
# ---------------------------------------------------------------------------


def test_rejecting_requires_a_reason_and_a_distinct_approver(db: Session) -> None:
    case = _Case(db)
    link = case.request()
    db.commit()

    with pytest.raises(ValidationFailedError):
        grd.reject_guardian_link(
            db,
            school_id=case.school.id,
            link_id=link.id,
            expected_version=link.version,
            reason_code="  ",
            actor_account_id=APPROVER,
            request_id=_rid(),
        )
    with pytest.raises(ForbiddenError):
        grd.reject_guardian_link(
            db,
            school_id=case.school.id,
            link_id=link.id,
            expected_version=link.version,
            reason_code="NO_EVIDENCE",
            actor_account_id=REQUESTER,
            request_id=_rid(),
        )


def test_a_rejection_emits_no_event(db: Session) -> None:
    """§7.3 lists activation and revocation, not refusal.

    Nothing downstream ever acted on a pending link, so there is nothing to
    tell anyone to stop doing — and an event announcing that a named adult was
    refused guardianship of a named child is a disclosure with no consumer.
    """
    case = _Case(db)
    link = case.request()
    db.commit()
    grd.reject_guardian_link(
        db,
        school_id=case.school.id,
        link_id=link.id,
        expected_version=link.version,
        reason_code="NO_EVIDENCE",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert link.status is LinkStatus.REJECTED
    assert link.rejected_at is not None
    assert db.execute(select(func.count()).select_from(OutboxMessage)).scalar_one() == 0


def test_revoking_a_link_closes_its_primary_designation(db: Session) -> None:
    """§3.10, and the reason it is one transaction.

    §3.1 allows a child to have no primary contact and names a *stale* one as
    the state that must never occur. A designation still pointing at a revoked
    link is precisely that, so it cannot wait for a consumer.
    """
    case = _Case(db)
    link = case.active_link()
    designation = pgc.designate_primary_guardian_contact(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        guardian_child_link_id=link.id,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

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

    assert link.status is LinkStatus.REVOKED
    assert designation.status is DesignationStatus.REVOKED
    assert designation.end_reason_code == "LINK_REVOKED"
    assert designation.ended_at is not None

    event = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.event_type == GUARDIAN_LINK_REVOKED_EVENT
        )
    ).scalar_one()
    assert event.payload["closed_designations"] == 1
    assert event.payload["version"] == link.version


def test_a_pending_link_may_be_revoked_too(db: Session) -> None:
    """§5.3's table allows REVOKED from PENDING_VERIFICATION as well as from
    ACTIVE — a request withdrawn before anyone decided."""
    case = _Case(db)
    link = case.request()
    db.commit()

    grd.revoke_guardian_link(
        db,
        school_id=case.school.id,
        link_id=link.id,
        expected_version=link.version,
        reason_code="WITHDRAWN",
        actor_account_id=REQUESTER,
        request_id=_rid(),
    )
    db.commit()
    assert link.status is LinkStatus.REVOKED


def test_a_revoked_link_is_terminal(db: Session) -> None:
    case = _Case(db)
    link = case.active_link()
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

    with pytest.raises(InvalidRelationshipTransitionError):
        grd.revoke_guardian_link(
            db,
            school_id=case.school.id,
            link_id=link.id,
            expected_version=link.version,
            reason_code="GUARDIANSHIP_ENDED",
            actor_account_id=APPROVER,
            request_id=_rid(),
        )


def test_a_revoked_pair_may_be_verified_again_as_a_new_row(db: Session) -> None:
    """§5.3: "nova provera je novi ID". The partial unique frees the key and
    the command permits the second request only because the first is closed."""
    case = _Case(db)
    first = case.active_link()
    grd.revoke_guardian_link(
        db,
        school_id=case.school.id,
        link_id=first.id,
        expected_version=first.version,
        reason_code="GUARDIANSHIP_ENDED",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    second = case.request()
    db.commit()
    assert second.id != first.id


# ---------------------------------------------------------------------------
# GRD-05 / GRD-06
# ---------------------------------------------------------------------------


def test_a_designation_requires_an_active_link(db: Session) -> None:
    case = _Case(db)
    link = case.request()
    db.commit()

    with pytest.raises(InvalidRelationshipTransitionError):
        pgc.designate_primary_guardian_contact(
            db,
            school_id=case.school.id,
            child_person_id=case.child.id,
            guardian_child_link_id=link.id,
            actor_account_id=APPROVER,
            request_id=_rid(),
        )


def test_replacing_a_primary_supersedes_the_old_row_in_one_transaction(
    db: Session,
) -> None:
    case = _Case(db)
    first_link = case.active_link()
    other = make_person(db, given="Ana", family="Petrović")
    ensure_person_profile(db, school=case.school, person=other)
    mem.create_membership(
        db,
        school_id=case.school.id,
        person_id=other.id,
        membership_type=MembershipType.GUARDIAN,
    )
    db.commit()
    second_link = case.request(guardian_person_id=other.id)
    case.activate(second_link)
    db.commit()

    first = pgc.designate_primary_guardian_contact(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        guardian_child_link_id=first_link.id,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()
    second = pgc.designate_primary_guardian_contact(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        guardian_child_link_id=second_link.id,
        actor_account_id=APPROVER,
        request_id=_rid(),
        expected_current_designation_id=first.id,
    )
    db.commit()

    assert first.status is DesignationStatus.SUPERSEDED
    assert first.end_reason_code == "REPLACED"
    assert second.status is DesignationStatus.ACTIVE
    assert (
        db.execute(
            select(func.count()).select_from(PrimaryGuardianContactDesignation)
        ).scalar_one()
        == 2
    )


def test_replacing_the_wrong_current_primary_is_refused(db: Session) -> None:
    """§5.4's "expected current", and the race it closes.

    Two staff members replacing different primaries at once would both succeed
    at "replace whatever is there", and the second would silently undo the
    first. Naming the row you believe you are replacing makes the loser lose
    loudly.
    """
    case = _Case(db)
    link = case.active_link()
    pgc.designate_primary_guardian_contact(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        guardian_child_link_id=link.id,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    with pytest.raises(RelationshipExistsError):
        pgc.designate_primary_guardian_contact(
            db,
            school_id=case.school.id,
            child_person_id=case.child.id,
            guardian_child_link_id=link.id,
            actor_account_id=APPROVER,
            request_id=_rid(),
            expected_current_designation_id=None,
        )


def test_removing_a_primary_leaves_the_child_with_none(db: Session) -> None:
    """§3.1: "primarni kontakt može privremeno biti nula, nikad stale"."""
    case = _Case(db)
    link = case.active_link()
    designation = pgc.designate_primary_guardian_contact(
        db,
        school_id=case.school.id,
        child_person_id=case.child.id,
        guardian_child_link_id=link.id,
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    pgc.remove_primary_guardian_contact(
        db,
        school_id=case.school.id,
        designation_id=designation.id,
        expected_version=designation.version,
        reason_code="NO_LONGER_REACHABLE",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert designation.status is DesignationStatus.REVOKED
    assert (
        db.execute(
            select(func.count())
            .select_from(PrimaryGuardianContactDesignation)
            .where(
                PrimaryGuardianContactDesignation.status == DesignationStatus.ACTIVE
            )
        ).scalar_one()
        == 0
    )
    assert (
        db.execute(
            select(func.count())
            .select_from(OutboxMessage)
            .where(OutboxMessage.event_type == PRIMARY_GUARDIAN_CHANGED_EVENT)
        ).scalar_one()
        == 2
    )


def test_another_schools_link_is_not_found(db: Session) -> None:
    """§4: a 403 would confirm the id exists."""
    case = _Case(db, name="Klub Soko")
    other = _Case(db, name="Klub Lav")
    foreign = other.active_link()

    with pytest.raises(NotFoundError):
        grd.revoke_guardian_link(
            db,
            school_id=case.school.id,
            link_id=foreign.id,
            expected_version=foreign.version,
            reason_code="GUARDIANSHIP_ENDED",
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
