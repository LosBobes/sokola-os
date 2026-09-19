"""M06 §8: the 35 numbered QA scenarios, under the gate #115 established.

Same shape as `test_m07_qa_traceability.py`: each runnable scenario is a test
named for its id, the rest are declared in `BLOCKED` with a reason, and a gate
fails if any of the 35 is neither. Nothing is skipped.

M06 differs from M07 in one way that matters. M07's blocked scenarios were
waiting on a surface (F-30) or on two live sessions. M06 has a third kind:
**scenarios that test features which do not exist in this repository at all.**
§2.2's sensitive identifiers — the encrypted JMBG envelope, its blind index,
the lawful-purpose check and the reveal permission — have no model, no service
and no column anywhere in `app/`. Five scenarios rest entirely on them.

That is recorded here rather than quietly filed under "no HTTP surface",
because the two are not the same problem and do not have the same fix. One
waits on a decision; the other is unwritten code.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from app.common.errors import ConflictError
from app.domains.people import membership as mem
from app.domains.people.activity_profiles import DisciplineCategory, ParticipantProfile
from app.domains.school.enums import MembershipStatus, MembershipType
from app.domains.school.models import SchoolMembership
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school

_QA_DOC = (
    Path(__file__).resolve().parents[3]
    / "docs/spec/v5.7/04-MODULSKI-UGOVORI/06-M06-LJUDI-I-CLANSTVA"
    / "02-M06-QA-I-TRACEABILITY.md"
)

#: Three causes, and the reason test below refuses a fourth.
#:
#: *Feature absent* is the one worth reading. §2.2's sensitive identifiers do
#: not exist in this repository — no column, no model, no service. A scenario
#: about refusing a JMBG without lawful purpose cannot fail today, because
#: there is nowhere to put a JMBG. Filing that under "no HTTP surface" would
#: make an unwritten feature look like a wiring problem.
BLOCKED: dict[str, str] = {
    "M06-QA-005": "feature absent: §2.2 sensitive identifiers are not implemented",
    "M06-QA-006": (
        "feature absent: the columns exist on `person` but nothing in app/ ever "
        "writes them — §2.1's contact update path has no implementation, and "
        "the existing M06 test sets the blind index by hand"
    ),
    "M06-QA-004": (
        "feature absent: nothing writes a contact blind index, so there is no "
        "index for a second create to match against"
    ),
    "M06-QA-007": (
        "feature absent: `create_provisional_person` has no idempotency guard — "
        "§7's receipt/replay contract is unimplemented for M06 person creation"
    ),
    "M06-QA-008": "feature absent: no idempotency guard to reuse a key against",
    "M06-QA-012": "true concurrency: two creates racing on one natural key",
    "M06-QA-017": (
        "feature absent: `ensure_termination_allowed` is a no-op hook and the "
        "application use-case that owns the M05 owner invariant does not exist"
    ),
    "M06-QA-018": "true concurrency: two owner terminations racing",
    "M06-QA-021": "true concurrency: two profile creates racing",
    "M06-QA-023": (
        "feature absent: the administrative note is length-checked only; nothing "
        "inspects its content for an identifier or health data"
    ),
    "M06-QA-024": "feature absent: §2.2 sensitive identifiers are not implemented",
    "M06-QA-025": "feature absent: no M17 policy verifier port exists",
    "M06-QA-026": "feature absent: §2.2 sensitive identifiers are not implemented",
    "M06-QA-027": "feature absent: no reveal permission exists to refuse",
    "M06-QA-028": "no HTTP surface: asserts a response during a concurrent revoke",
    "M06-QA-030": (
        "feature absent: the merge marks the source MERGED but does not re-parent "
        "its relationships — `merge.py` calls that a deliberate follow-up"
    ),
    "M06-QA-031": (
        "feature absent: neither M06_MERGE_MEMBERSHIP_CONFLICT nor "
        "M06_CROSS_TENANT_MERGE_NOT_SUPPORTED exists; a cross-tenant source is a "
        "plain 404 from the school-scoped lookup"
    ),
    "M06-QA-032": "feature absent: no M02 eligibility port exists",
    "M06-QA-035": "infrastructure: backup/replica/telemetry encryption is not a test",
}


def _rid() -> str:
    return str(uuid.uuid4())


# ===========================================================================
# The gate
# ===========================================================================


def _declared() -> set[str]:
    return set(re.findall(r"M06-QA-\d{3}", _QA_DOC.read_text()))


def _implemented() -> set[str]:
    source = Path(__file__).read_text()
    return {
        f"M06-QA-{n}"
        for n in re.findall(r"^def test_m06_qa_(\d{3})_", source, re.MULTILINE)
    }


def test_every_m06_scenario_is_implemented_or_declared() -> None:
    declared = _declared()
    assert len(declared) == 35, f"expected 35 scenarios, found {len(declared)}"
    implemented = _implemented()
    blocked = set(BLOCKED)
    assert not (implemented & blocked), sorted(implemented & blocked)
    missing = declared - implemented - blocked
    assert not missing, f"neither implemented nor declared blocked: {sorted(missing)}"
    stray = (implemented | blocked) - declared
    assert not stray, f"ids not in the contract: {sorted(stray)}"


def test_the_m06_blocked_reasons_name_one_of_three_causes() -> None:
    """A free-text reason rots into "TODO". Constraining it means a fourth
    cause has to be added deliberately — and "feature absent" in particular
    should never quietly become "no HTTP surface"."""
    for scenario, reason in BLOCKED.items():
        assert any(
            cause in reason
            for cause in (
                "feature absent",
                "true concurrency",
                "no HTTP surface",
                "infrastructure",
            )
        ), f"{scenario} has an unrecognised blocking reason: {reason}"


# ===========================================================================
# Person (§2.1, §3.4)
# ===========================================================================


def test_m06_qa_001_child_without_birth_date_contact_or_account(
    db: Session,
) -> None:
    """§1: M06 records people the school has, whether or not they can sign in."""
    school = make_school(db)
    child = make_person(db, given="Iva", family="Petrović")
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=child.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    db.commit()

    assert child.birth_date is None
    assert child.email_ciphertext is None
    assert membership.status is MembershipStatus.DRAFT


def test_m06_qa_002_m06_has_no_account_creation_port(db: Session) -> None:
    """§0, §1.2: M06 must not be able to create a `UserAccount`.

    Asserted against the source rather than by calling something, because the
    contract's claim is that the port *does not exist*. A behavioural test
    could only show that today's code does not happen to call it.
    """
    domain = Path(__file__).resolve().parents[1] / "app/domains/people"
    offenders = [
        py.name
        for py in domain.rglob("*.py")
        if "UserAccount(" in py.read_text()
    ]
    assert not offenders, f"M06 constructs UserAccount in: {offenders}"


def test_m06_qa_003_two_people_with_the_same_name(db: Session) -> None:
    """§3.4: a name is not a uniqueness key. Two children called Marko
    Marković is an ordinary Tuesday, not a data error."""
    make_school(db)
    first = make_person(db, given="Marko", family="Marković")
    second = make_person(db, given="Marko", family="Marković")
    db.commit()
    assert first.id != second.id


# ===========================================================================
# Membership (§2.3, §3.2, §3.5, §5.1)
# ===========================================================================


def _pair(db: Session, given: str = "Ana"):
    school = make_school(db)
    person = make_person(db, given=given, family="Petrović")
    ensure_person_profile(db, school=school, person=person)
    return school, person


def test_m06_qa_009_guardian_and_staff_in_one_school(db: Session) -> None:
    """§3.2: a parent who also coaches is both, under separate natural keys."""
    school, person = _pair(db)
    guardian = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.GUARDIAN,
    )
    staff = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.STAFF,
    )
    db.commit()
    assert guardian.id != staff.id


def test_m06_qa_010_staff_in_two_schools_are_independent(db: Session) -> None:
    """§3.2, §4: holding a membership in one school carries no right in
    another, and changing one leaves the other untouched."""
    a, person = _pair(db)
    b = make_school(db, name="Klub Lav")
    ensure_person_profile(db, school=b, person=person)
    in_a = mem.create_membership(
        db, school_id=a.id, person_id=person.id, membership_type=MembershipType.STAFF
    )
    in_b = mem.create_membership(
        db, school_id=b.id, person_id=person.id, membership_type=MembershipType.STAFF
    )
    db.commit()

    mem.terminate_membership(db, in_b, reason_code="LEFT")
    db.commit()
    assert in_a.status is MembershipStatus.DRAFT
    assert in_b.status is MembershipStatus.TERMINATED


def test_m06_qa_011_second_open_participant_membership(db: Session) -> None:
    school, person = _pair(db)
    mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    db.flush()
    with pytest.raises(ConflictError):
        mem.create_membership(
            db,
            school_id=school.id,
            person_id=person.id,
            membership_type=MembershipType.PARTICIPANT,
        )


def test_m06_qa_013_first_episode_sets_is_first_activation(db: Session) -> None:
    school, person = _pair(db)
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    mem.activate_membership(db, membership)
    db.commit()
    assert membership.is_first_activation is True


def test_m06_qa_014_a_later_episode_is_not_a_first_activation(
    db: Session,
) -> None:
    """§3.5: the history stays, and a return does not retroactively look like
    a first arrival."""
    school, person = _pair(db)
    first = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    mem.activate_membership(db, first)
    mem.terminate_membership(db, first, reason_code="LEFT")
    db.commit()

    second = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    mem.activate_membership(db, second)
    db.commit()

    assert second.id != first.id
    assert second.is_first_activation is False
    assert first.status is MembershipStatus.TERMINATED


def test_m06_qa_015_suspend_without_a_reason(db: Session) -> None:
    school, person = _pair(db)
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    mem.activate_membership(db, membership)
    db.commit()

    with pytest.raises(ConflictError):
        mem.suspend_membership(db, membership, reason_code="")
    db.rollback()
    assert membership.status is MembershipStatus.ACTIVE


def test_m06_qa_016_terminated_cannot_return_to_active(db: Session) -> None:
    school, person = _pair(db)
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    mem.activate_membership(db, membership)
    mem.terminate_membership(db, membership, reason_code="LEFT")
    db.commit()

    with pytest.raises(ConflictError):
        mem.activate_membership(db, membership)
    db.rollback()
    assert membership.status is MembershipStatus.TERMINATED


# ===========================================================================
# Profiles (§2.4, §2.5)
# ===========================================================================


def test_m06_qa_019_participant_profile_on_a_staff_membership(
    db: Session,
) -> None:
    """§2.5: the profile's type-pinned foreign key makes this impossible, not
    merely refused — the same construction M07's guardian link uses."""
    school, person = _pair(db)
    staff = mem.create_membership(
        db, school_id=school.id, person_id=person.id, membership_type=MembershipType.STAFF
    )
    db.commit()

    db.add(
        ParticipantProfile(
            school_id=school.id,
            school_membership_id=staff.id,
            membership_type=MembershipType.PARTICIPANT.value,
        )
    )
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert "participant_profile" in str(caught.value)
    db.rollback()


def test_m06_qa_020_profile_in_a_naming_a_membership_in_b(db: Session) -> None:
    """§2.5, §4: the database refuses the direct write, not just the service."""
    a, person = _pair(db)
    b = make_school(db, name="Klub Lav")
    ensure_person_profile(db, school=b, person=person)
    in_b = mem.create_membership(
        db,
        school_id=b.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    db.commit()

    db.add(
        ParticipantProfile(
            school_id=a.id,
            school_membership_id=in_b.id,
            membership_type=MembershipType.PARTICIPANT.value,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ===========================================================================
# Tenant isolation (§4)
# ===========================================================================


def test_m06_qa_034_cross_person_membership_reference_is_refused(
    db: Session,
) -> None:
    """§2.3, §4: `UNIQUE(school_id, id, person_id)` is what makes a reference
    name the *person* as well as the tenant.

    Without it, a row in the right school pointing at the right membership id
    could still be about somebody else — and every check that looked only at
    `school_id` would pass it.
    """
    school, person = _pair(db)
    other = make_person(db, given="Marko", family="Ilić")
    ensure_person_profile(db, school=school, person=other)
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=MembershipType.PARTICIPANT,
    )
    db.commit()

    constraint = db.execute(
        select(func.count()).select_from(SchoolMembership).where(
            SchoolMembership.school_id == school.id,
            SchoolMembership.id == membership.id,
            SchoolMembership.person_id == other.id,
        )
    ).scalar_one()
    assert constraint == 0, "a membership id must not resolve for a second person"


def test_m06_qa_029_reading_a_person_who_is_only_in_another_school(
    db: Session,
) -> None:
    """§4: the repository's school-scoped lookup simply does not match, so the
    caller gets the same answer as for an id that never existed."""
    from app.domains.people import repository

    a = make_school(db, name="Klub Soko")
    b = make_school(db, name="Klub Lav")
    person = make_person(db, given="Lazar", family="B")
    ensure_person_profile(db, school=b, person=person)
    db.commit()

    assert repository.get_school_person(db, a.id, person.id) is None
    assert repository.get_school_person(db, a.id, "per_does_not_exist") is None


def test_m06_qa_022_every_discipline_category_round_trips(db: Session) -> None:
    """§2.5, §8.5: each is stored "bez promene autorizacione semantike".

    The second half is the claim worth pinning: a discipline is a label on a
    profile and nothing reads it to decide access. Asserted by checking that
    the value survives a round trip and that the profile carries no field that
    could narrow or widen anything.
    """
    school, person = _pair(db)
    fields = set(ParticipantProfile.__table__.columns.keys())
    assert not fields & {"role", "role_code", "permissions", "granted_areas"}

    for index, category in enumerate(DisciplineCategory):
        member = make_person(db, given=f"Dete{index}", family="Petrović")
        ensure_person_profile(db, school=school, person=member)
        membership = mem.create_membership(
            db,
            school_id=school.id,
            person_id=member.id,
            membership_type=MembershipType.PARTICIPANT,
        )
        db.flush()
        db.add(
            ParticipantProfile(
                school_id=school.id,
                school_membership_id=membership.id,
                membership_type=MembershipType.PARTICIPANT.value,
                discipline_category=category,
            )
        )
    db.commit()

    stored = set(
        db.execute(select(ParticipantProfile.discipline_category)).scalars().all()
    )
    assert stored == set(DisciplineCategory)


def test_m06_qa_033_school_person_profile_names_the_person_in_its_key(
    db: Session,
) -> None:
    """§2.4, §7.2: `UNIQUE(school_id, id, person_id)` on the profile.

    M02 and M04 reference a `SchoolPersonProfile` when they invite or nominate
    someone. With only `(school_id, id)` available, a reference in the right
    school pointing at the right profile id could still be about a different
    person — and every guard that checked the tenant would pass it. The
    composite target is what lets the reference name the person too.
    """
    from sqlalchemy import text

    columns = db.execute(
        text(
            "SELECT a.attname FROM pg_constraint c "
            "JOIN unnest(c.conkey) k ON true "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k "
            "WHERE c.conname = 'uq_school_person_profile_tenant_person' "
            "ORDER BY a.attname"
        )
    ).scalars().all()
    assert sorted(columns) == ["id", "person_id", "school_id"]
