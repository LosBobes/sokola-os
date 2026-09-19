"""M07 §7.1: the FAM commands, and the rules the database could not take.

The schema tests established what rows the database will hold. These establish
what the *commands* refuse, which is a different list — every rule here is one
a CHECK constraint cannot express, either because it spans tables or because it
spans modules.

The sharpest is §3.13's archive rule. A family may be archived only when
nothing rests on it: no active membership, no open payer link, and no
outstanding M12 obligation. The third cannot be checked from inside this
module — an `app.domains.family` that imported M12 would be the
`M12 -> M07 -> M12` cycle the contract routes around — so it arrives as a
required port. The tests below cover all three, including what happens when
finance cannot be reached at all, which §6 says must fail closed.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from app.common.errors import (
    ConflictError,
    DependencyUnavailableError,
    FamilyArchiveBlockedError,
    IdempotencyConflictError,
    InvalidRelationshipTransitionError,
    NotFoundError,
    RelationshipExistsError,
    StaleVersionError,
    ValidationFailedError,
)
from app.domains.family import service
from app.domains.family.enums import (
    FAMILY_ARCHIVED_EVENT,
    FamilyMembershipStatus,
    FamilyStatus,
    LinkStatus,
    MemberKind,
    PayerBasisKind,
)
from app.domains.family.models import Family, PayerChildLink
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipStatus, MembershipType
from app.platform import clock
from app.platform.idempotency import service as idempotency
from app.platform.outbox.models import OutboxMessage
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school

ACTOR = "acc_staff"


def _rid() -> str:
    """A fresh idempotency key. §7 makes `request_id` the canonical one, so a
    test that reused a key would be testing replay, not the command."""
    return str(uuid.uuid4())


def _no_obligations(_school_id: str, _family_id: str) -> bool:
    return False


def _has_obligations(_school_id: str, _family_id: str) -> bool:
    return True


def _finance_is_down(_school_id: str, _family_id: str) -> bool:
    raise RuntimeError("M12 unreachable")


def _school_and_person(db: Session, given: str = "Ana"):
    school = make_school(db)
    person = make_person(db, given=given, family="Petrović")
    ensure_person_profile(db, school=school, person=person)
    mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    db.commit()
    return school, person


# ---------------------------------------------------------------------------
# FAM-01 / FAM-03: creating a grouping and putting someone in it
# ---------------------------------------------------------------------------


def test_create_family_makes_a_grouping_and_nothing_else(db: Session) -> None:
    """§3.1: five separate facts. Creating the first implies none of the rest."""
    school, _ = _school_and_person(db)
    family = service.create_family(
        db,
        school_id=school.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
        display_label="Petrović",
    )
    db.commit()

    assert family.status is FamilyStatus.ACTIVE
    assert family.version == 1
    assert family.created_by_account_id == ACTOR


def test_an_empty_label_is_refused_but_an_absent_one_is_not(db: Session) -> None:
    school, _ = _school_and_person(db)
    unlabelled = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()
    assert unlabelled.display_label is None

    with pytest.raises(ValidationFailedError):
        service.create_family(
            db,
            school_id=school.id,
            actor_account_id=ACTOR,
            request_id=_rid(),
            display_label="   ",
        )


def test_a_repeated_request_id_replays_rather_than_creating_twice(
    db: Session,
) -> None:
    """§7: `request_id` is the canonical idempotency key.

    A client that retries after a timeout must not end up with two households.
    """
    school, _ = _school_and_person(db)
    request_id = _rid()
    first = service.create_family(
        db,
        school_id=school.id,
        actor_account_id=ACTOR,
        request_id=request_id,
        display_label="Petrović",
    )
    db.commit()
    second = service.create_family(
        db,
        school_id=school.id,
        actor_account_id=ACTOR,
        request_id=request_id,
        display_label="Petrović",
    )
    db.commit()

    assert first.id == second.id
    assert db.execute(select(func.count()).select_from(Family)).scalar_one() == 1


def test_the_same_key_with_different_data_is_a_conflict(db: Session) -> None:
    """§7: "Retry istog hash-a vraća isti rezultat; drugi hash je 409."

    Replaying the *changed* payload would silently apply neither the first
    request nor the second, and report success for whichever the client asked
    about last.
    """
    school, _ = _school_and_person(db)
    request_id = _rid()
    service.create_family(
        db,
        school_id=school.id,
        actor_account_id=ACTOR,
        request_id=request_id,
        display_label="Petrović",
    )
    db.commit()

    with pytest.raises(IdempotencyConflictError):
        service.create_family(
            db,
            school_id=school.id,
            actor_account_id=ACTOR,
            request_id=request_id,
            display_label="Jovanović",
        )


def test_a_member_needs_an_open_school_membership(db: Session) -> None:
    """§2.2: the M06 membership must be open at creation.

    The composite foreign key cannot catch this — it proves the membership
    belongs to this person and this tenant, not that the school still has
    them. So a terminated membership has to be refused here or not at all.
    """
    school = make_school(db)
    person = make_person(db, given="Ana", family="Petrović")
    ensure_person_profile(db, school=school, person=person)
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    membership.status = MembershipStatus.TERMINATED
    membership.termination_reason_code = "LEFT"
    membership.end_date = clock.now().date()
    db.commit()

    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()

    with pytest.raises(NotFoundError):
        service.add_family_member(
            db,
            school_id=school.id,
            family_id=family.id,
            person_id=person.id,
            member_kind=MemberKind.DEPENDENT,
            actor_account_id=ACTOR,
            request_id=_rid(),
        )


def test_a_person_cannot_join_the_same_family_twice(db: Session) -> None:
    school, person = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    service.add_family_member(
        db,
        school_id=school.id,
        family_id=family.id,
        person_id=person.id,
        member_kind=MemberKind.DEPENDENT,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()

    with pytest.raises(RelationshipExistsError):
        service.add_family_member(
            db,
            school_id=school.id,
            family_id=family.id,
            person_id=person.id,
            member_kind=MemberKind.DEPENDENT,
            actor_account_id=ACTOR,
            request_id=_rid(),
        )


def test_a_person_may_join_a_second_family(db: Session) -> None:
    """§2.2: separated households. The refusal above is scoped to one family,
    not to the person."""
    school, person = _school_and_person(db)
    first = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    second = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    for family in (first, second):
        service.add_family_member(
            db,
            school_id=school.id,
            family_id=family.id,
            person_id=person.id,
            member_kind=MemberKind.DEPENDENT,
            actor_account_id=ACTOR,
            request_id=_rid(),
        )
    db.commit()


def test_an_archived_family_takes_no_new_members(db: Session) -> None:
    school, person = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()
    service.archive_family(
        db,
        school_id=school.id,
        family_id=family.id,
        expected_version=1,
        reason_code="MERGED",
        actor_account_id=ACTOR,
        request_id=_rid(),
        has_open_obligations=_no_obligations,
    )
    db.commit()

    with pytest.raises(InvalidRelationshipTransitionError):
        service.add_family_member(
            db,
            school_id=school.id,
            family_id=family.id,
            person_id=person.id,
            member_kind=MemberKind.DEPENDENT,
            actor_account_id=ACTOR,
            request_id=_rid(),
        )


# ---------------------------------------------------------------------------
# FAM-02: §3.13's three blockers
# ---------------------------------------------------------------------------


def test_an_active_member_blocks_archiving(db: Session) -> None:
    school, person = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    service.add_family_member(
        db,
        school_id=school.id,
        family_id=family.id,
        person_id=person.id,
        member_kind=MemberKind.DEPENDENT,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()

    with pytest.raises(FamilyArchiveBlockedError, match="aktivnih članova"):
        service.archive_family(
            db,
            school_id=school.id,
            family_id=family.id,
            expected_version=1,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_no_obligations,
        )


def test_an_open_payer_link_blocks_archiving(db: Session) -> None:
    """Only a payer link names a family, so it is the only link that can rest
    "isključivo" on one — a guardian link has no `family_id` at all."""
    school = make_school(db)
    payer = make_person(db, given="Nikola", family="Jovanović")
    child = make_person(db, given="Iva", family="Petrović")
    for person in (payer, child):
        ensure_person_profile(db, school=school, person=person)
    payer_membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=payer.id,
        membership_type=MembershipType.CONTACT,
    )
    child_membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=child.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    db.commit()

    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.flush()
    db.add(
        PayerChildLink(
            school_id=school.id,
            payer_person_id=payer.id,
            child_person_id=child.id,
            payer_school_membership_id=payer_membership.id,
            child_school_membership_id=child_membership.id,
            payer_membership_type=MembershipType.CONTACT.value,
            child_membership_type=MembershipType.PARTICIPANT.value,
            family_id=family.id,
            basis_kind=PayerBasisKind.FAMILY_ADULT,
            status=LinkStatus.ACTIVE,
            activated_at=clock.now(),
            decision_by_account_id="acc_approver",
            requested_by_account_id=ACTOR,
            requested_at=clock.now(),
        )
    )
    db.commit()

    with pytest.raises(FamilyArchiveBlockedError, match="platilačkih veza"):
        service.archive_family(
            db,
            school_id=school.id,
            family_id=family.id,
            expected_version=1,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_no_obligations,
        )


def test_an_open_financial_obligation_blocks_archiving(db: Session) -> None:
    """The blocker this module cannot see for itself.

    §3.13 routes it through application orchestration to avoid an
    `M12 -> M07 -> M12` cycle, and the port has no default — a caller who has
    not consulted finance cannot archive a family by forgetting to.
    """
    school, _ = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()

    with pytest.raises(FamilyArchiveBlockedError, match="finansijskih obaveza"):
        service.archive_family(
            db,
            school_id=school.id,
            family_id=family.id,
            expected_version=1,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_has_obligations,
        )


def test_an_unreachable_finance_guard_fails_closed(db: Session) -> None:
    """§6: `M07_DEPENDENCY_UNAVAILABLE` is 503, not a permissive guess.

    "Finance says there are no open obligations" and "finance could not be
    reached" must not produce the same outcome. The second one archiving the
    family anyway is how a household gets closed out from under an unpaid
    invoice.
    """
    school, _ = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()

    with pytest.raises(DependencyUnavailableError) as caught:
        service.archive_family(
            db,
            school_id=school.id,
            family_id=family.id,
            expected_version=1,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_finance_is_down,
        )
    assert caught.value.status_code == 503

    db.rollback()
    assert (
        db.execute(select(Family).where(Family.id == family.id)).scalar_one().status
        is FamilyStatus.ACTIVE
    )


def test_all_three_blockers_are_reported_together(db: Session) -> None:
    """One answer, not three round trips.

    An operator who clears the membership only to be told about the invoice
    has been made to discover the requirements one refusal at a time.
    """
    school, person = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    service.add_family_member(
        db,
        school_id=school.id,
        family_id=family.id,
        person_id=person.id,
        member_kind=MemberKind.ADULT,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()

    with pytest.raises(FamilyArchiveBlockedError) as caught:
        service.archive_family(
            db,
            school_id=school.id,
            family_id=family.id,
            expected_version=1,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_has_obligations,
        )
    message = str(caught.value)
    assert "aktivnih članova" in message
    assert "finansijskih obaveza" in message


def test_archiving_a_clear_family_bumps_the_version_and_emits_one_event(
    db: Session,
) -> None:
    school, _ = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()

    service.archive_family(
        db,
        school_id=school.id,
        family_id=family.id,
        expected_version=1,
        reason_code="MERGED",
        actor_account_id=ACTOR,
        request_id=_rid(),
        has_open_obligations=_no_obligations,
        correlation_id="corr-1",
    )
    db.commit()

    assert family.status is FamilyStatus.ARCHIVED
    assert family.version == 2
    assert family.archive_reason_code == "MERGED"

    events = (
        db.execute(
            select(OutboxMessage).where(
                OutboxMessage.event_type == FAMILY_ARCHIVED_EVENT
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["family_id"] == family.id
    assert payload["version"] == 2
    assert payload["reason_code"] == "MERGED"
    # §4 / §7.3: opaque IDs and codes only. The label is the school's own
    # words about a household and never leaves the module.
    assert "display_label" not in payload


def test_archiving_twice_is_refused_rather_than_silently_repeated(
    db: Session,
) -> None:
    """§5.1: ARCHIVED is terminal in H0. A no-op would report success for
    something that did not happen."""
    school, _ = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()
    service.archive_family(
        db,
        school_id=school.id,
        family_id=family.id,
        expected_version=1,
        reason_code="MERGED",
        actor_account_id=ACTOR,
        request_id=_rid(),
        has_open_obligations=_no_obligations,
    )
    db.commit()

    with pytest.raises(InvalidRelationshipTransitionError):
        service.archive_family(
            db,
            school_id=school.id,
            family_id=family.id,
            expected_version=2,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_no_obligations,
        )


def test_a_stale_version_is_refused(db: Session) -> None:
    school, _ = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()

    with pytest.raises(StaleVersionError):
        service.archive_family(
            db,
            school_id=school.id,
            family_id=family.id,
            expected_version=99,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_no_obligations,
        )


def test_another_schools_family_is_not_found_rather_than_forbidden(
    db: Session,
) -> None:
    """§4: "Nepostojeći, cross-tenant i ... daju isti 404".

    A 403 here would confirm that the id exists, which is the leak the
    enumeration-safe answer is there to prevent.
    """
    school, _ = _school_and_person(db)
    other = make_school(db, name="Klub Lav")
    db.commit()
    family = service.create_family(
        db, school_id=other.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()

    with pytest.raises(NotFoundError):
        service.archive_family(
            db,
            school_id=school.id,
            family_id=family.id,
            expected_version=1,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_no_obligations,
        )


# ---------------------------------------------------------------------------
# FAM-04
# ---------------------------------------------------------------------------


def test_ending_a_membership_records_when_and_why(db: Session) -> None:
    school, person = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    membership = service.add_family_member(
        db,
        school_id=school.id,
        family_id=family.id,
        person_id=person.id,
        member_kind=MemberKind.DEPENDENT,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()

    service.end_family_membership(
        db,
        school_id=school.id,
        membership_id=membership.id,
        expected_version=1,
        reason_code="MOVED_OUT",
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()

    assert membership.status is FamilyMembershipStatus.ENDED
    assert membership.end_reason_code == "MOVED_OUT"
    assert membership.effective_until is not None
    assert membership.version == 2


def test_a_membership_cannot_end_before_it_began(db: Session) -> None:
    school, person = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    membership = service.add_family_member(
        db,
        school_id=school.id,
        family_id=family.id,
        person_id=person.id,
        member_kind=MemberKind.DEPENDENT,
        actor_account_id=ACTOR,
        request_id=_rid(),
        effective_from=dt.date(2026, 6, 1),
    )
    db.commit()

    with pytest.raises(ValidationFailedError):
        service.end_family_membership(
            db,
            school_id=school.id,
            membership_id=membership.id,
            expected_version=1,
            reason_code="MOVED_OUT",
            actor_account_id=ACTOR,
            request_id=_rid(),
            effective_until=dt.date(2026, 1, 1),
        )


def test_ending_a_membership_twice_is_refused(db: Session) -> None:
    school, person = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    membership = service.add_family_member(
        db,
        school_id=school.id,
        family_id=family.id,
        person_id=person.id,
        member_kind=MemberKind.DEPENDENT,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    service.end_family_membership(
        db,
        school_id=school.id,
        membership_id=membership.id,
        expected_version=1,
        reason_code="MOVED_OUT",
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()

    with pytest.raises(InvalidRelationshipTransitionError):
        service.end_family_membership(
            db,
            school_id=school.id,
            membership_id=membership.id,
            expected_version=2,
            reason_code="MOVED_OUT",
            actor_account_id=ACTOR,
            request_id=_rid(),
        )


def test_an_ended_membership_frees_the_key_for_a_return(db: Session) -> None:
    """§5.2 end to end: leaving and coming back is two rows, and the command
    permits the second only because the first is closed."""
    school, person = _school_and_person(db)
    family = service.create_family(
        db, school_id=school.id, actor_account_id=ACTOR, request_id=_rid()
    )
    membership = service.add_family_member(
        db,
        school_id=school.id,
        family_id=family.id,
        person_id=person.id,
        member_kind=MemberKind.DEPENDENT,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    service.end_family_membership(
        db,
        school_id=school.id,
        membership_id=membership.id,
        expected_version=1,
        reason_code="MOVED_OUT",
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()

    returned = service.add_family_member(
        db,
        school_id=school.id,
        family_id=family.id,
        person_id=person.id,
        member_kind=MemberKind.DEPENDENT,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    assert returned.id != membership.id


def test_an_unfinished_receipt_blocks_a_second_attempt(db: Session) -> None:
    """§7 / §6 `M07_IDEMPOTENCY_IN_PROGRESS`: an in-flight command under the
    same key is refused, not run again.

    This exercises the guard rather than a real race — two live sessions
    cannot be driven from one test without threading, and the second would
    simply block on the unique index until the first committed. What it does
    establish is the branch nothing else in the suite reaches: a receipt that
    exists and is *not* completed is a refusal, not a replay. Without that,
    a client retrying during a slow first attempt would run the command twice.
    """
    school, _ = _school_and_person(db)
    request_id = _rid()
    params = {"display_label": None, "actor_account_id": ACTOR}

    first = idempotency.begin(
        db, school.id, "m07.family.create", request_id, params
    )
    assert first.replay is None

    with pytest.raises(ConflictError):
        idempotency.begin(db, school.id, "m07.family.create", request_id, params)
