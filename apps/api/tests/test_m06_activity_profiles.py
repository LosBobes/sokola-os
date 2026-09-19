"""M06 §2.5–2.7: the profiles that hang off a membership, and merge history.

The property worth protecting is that a profile **cannot be attached to the
wrong kind of membership**. §6 has an error code for that mismatch, and the
composite foreign key here is an attempt to make the code unreachable: the
membership's type is part of the reference, so a participant profile on a STAFF
membership is not merely rejected by a service check — it cannot be written at
all, by any path.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import BadRequestError, ConflictError, NotFoundError
from app.common.ids import new_id
from app.domains.people import membership as mem
from app.domains.people import profile_service
from app.domains.people.activity_profiles import (
    ParticipantProfile,
    PersonMergeHistoryEntry,
    StaffProfile,
)
from app.domains.people.profile_enums import (
    DisciplineCategory,
    EngagementType,
    PersonMergeReason,
)
from app.domains.school.enums import MembershipStatus, MembershipType
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school


def _membership(db: Session, school, kind: MembershipType, name: str = "Ana"):
    person = make_person(db, given=name)
    ensure_person_profile(db, school=school, person=person)
    membership = mem.create_membership(
        db,
        school_id=school.id,
        person_id=person.id,
        membership_type=kind,
        status=MembershipStatus.ACTIVE,
    )
    db.flush()
    return membership


# ---------------------------------------------------------------------------
# Type matching (§3.6) — the point of the composite key
# ---------------------------------------------------------------------------


def test_a_participant_profile_attaches_to_a_participant_membership(db: Session) -> None:
    school = make_school(db)
    membership = _membership(db, school, MembershipType.PARTICIPANT)

    profile = profile_service.create_participant_profile(
        db,
        school_id=school.id,
        membership_id=membership.id,
        discipline_category=DisciplineCategory.DANCE,
        level_label="II grupa",
    )
    db.commit()

    assert profile.discipline_category is DisciplineCategory.DANCE
    assert profile_service.get_participant_profile(db, school.id, membership.id) is profile


def test_a_participant_profile_is_refused_on_a_staff_membership(db: Session) -> None:
    school = make_school(db)
    staff = _membership(db, school, MembershipType.STAFF)

    with pytest.raises(ConflictError, match="PARTICIPANT"):
        profile_service.create_participant_profile(
            db, school_id=school.id, membership_id=staff.id
        )


def test_a_staff_profile_is_refused_on_a_participant_membership(db: Session) -> None:
    school = make_school(db)
    participant = _membership(db, school, MembershipType.PARTICIPANT)

    with pytest.raises(ConflictError, match="STAFF"):
        profile_service.create_staff_profile(
            db, school_id=school.id, membership_id=participant.id
        )


def test_the_database_refuses_a_profile_on_the_wrong_membership_type(db: Session) -> None:
    """The service check is a nicety; this foreign key is the guarantee. The
    membership's type is part of the reference, so no path can write it."""
    school = make_school(db)
    staff = _membership(db, school, MembershipType.STAFF)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO participant_profile (id, school_id, school_membership_id, "
                "membership_type, version, created_at, updated_at) "
                "VALUES (:id, :s, :m, 'PARTICIPANT', 1, now(), now())"
            ),
            {"id": new_id("pcp"), "s": school.id, "m": staff.id},
        )
    db.rollback()


def test_a_profile_cannot_reference_another_schools_membership(db: Session) -> None:
    left, right = make_school(db, name="Leva"), make_school(db, name="Desna")
    foreign = _membership(db, right, MembershipType.PARTICIPANT)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO participant_profile (id, school_id, school_membership_id, "
                "membership_type, version, created_at, updated_at) "
                "VALUES (:id, :s, :m, 'PARTICIPANT', 1, now(), now())"
            ),
            {"id": new_id("pcp"), "s": left.id, "m": foreign.id},
        )
    db.rollback()


def test_an_unknown_membership_reads_as_not_found(db: Session) -> None:
    """§4: a membership in another school and one that does not exist give the
    same answer, so the caller learns nothing either way."""
    school = make_school(db)
    with pytest.raises(NotFoundError):
        profile_service.create_participant_profile(
            db, school_id=school.id, membership_id=new_id("mem")
        )


def test_one_profile_per_membership(db: Session) -> None:
    school = make_school(db)
    membership = _membership(db, school, MembershipType.PARTICIPANT)
    profile_service.create_participant_profile(
        db, school_id=school.id, membership_id=membership.id
    )
    db.flush()

    with pytest.raises(ConflictError, match="već postoji"):
        profile_service.create_participant_profile(
            db, school_id=school.id, membership_id=membership.id
        )


# ---------------------------------------------------------------------------
# Staff specializations (§2.6)
# ---------------------------------------------------------------------------


def test_specializations_are_sorted_and_deduplicated(db: Session) -> None:
    """Two profiles listing the same specializations in different orders are the
    same profile; storing them differently makes every comparison re-sort."""
    school = make_school(db)
    membership = _membership(db, school, MembershipType.STAFF)

    profile = profile_service.create_staff_profile(
        db,
        school_id=school.id,
        membership_id=membership.id,
        engagement_type=EngagementType.VOLUNTEER,
        specialization_codes=["  GYMNASTICS ", "BALLET", "GYMNASTICS", "", "  "],
    )
    db.commit()
    assert profile.specialization_codes == ["BALLET", "GYMNASTICS"]
    assert profile.engagement_type is EngagementType.VOLUNTEER


def test_an_empty_specialization_list_stores_as_absent(db: Session) -> None:
    school = make_school(db)
    membership = _membership(db, school, MembershipType.STAFF)
    profile = profile_service.create_staff_profile(
        db, school_id=school.id, membership_id=membership.id, specialization_codes=["", " "]
    )
    db.flush()
    assert profile.specialization_codes is None


def test_too_many_specializations_are_refused(db: Session) -> None:
    school = make_school(db)
    membership = _membership(db, school, MembershipType.STAFF)

    with pytest.raises(BadRequestError, match="50"):
        profile_service.create_staff_profile(
            db,
            school_id=school.id,
            membership_id=membership.id,
            specialization_codes=[f"CODE_{i}" for i in range(51)],
        )


def test_the_database_caps_the_specialization_array(db: Session) -> None:
    school = make_school(db)
    membership = _membership(db, school, MembershipType.STAFF)
    profile = profile_service.create_staff_profile(
        db, school_id=school.id, membership_id=membership.id
    )
    db.commit()

    codes = "{" + ",".join(f"C{i}" for i in range(51)) + "}"
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE staff_profile SET specialization_codes = :codes WHERE id = :id"),
            {"codes": codes, "id": profile.id},
        )
    db.rollback()


# ---------------------------------------------------------------------------
# Effectiveness follows the membership (§5)
# ---------------------------------------------------------------------------


def test_a_profile_has_no_status_of_its_own(db: Session) -> None:
    """§5: there is one answer to "is this person active here", and it lives on
    the membership. A second status on the profile would be a second answer."""
    school = make_school(db)
    membership = _membership(db, school, MembershipType.PARTICIPANT)
    profile = profile_service.create_participant_profile(
        db, school_id=school.id, membership_id=membership.id
    )
    db.flush()

    assert not hasattr(profile, "status")
    mem.suspend_membership(db, membership, reason_code="PAUSE")
    db.flush()
    assert not mem.is_effective(membership)
    # The profile is untouched: its effectiveness is not its own to record.
    assert profile_service.get_participant_profile(db, school.id, membership.id) is profile


def test_terminating_a_membership_keeps_the_profile_reachable(db: Session) -> None:
    school = make_school(db)
    membership = _membership(db, school, MembershipType.PARTICIPANT)
    profile_service.create_participant_profile(
        db, school_id=school.id, membership_id=membership.id, level_label="I grupa"
    )
    mem.terminate_membership(db, membership, reason_code="LEFT")
    db.commit()

    stored = profile_service.get_participant_profile(db, school.id, membership.id)
    assert stored is not None and stored.level_label == "I grupa"


# ---------------------------------------------------------------------------
# Merge history (§2.7)
# ---------------------------------------------------------------------------


def _merge_entry(db: Session, school, surviving: str, merged: str) -> PersonMergeHistoryEntry:
    entry = PersonMergeHistoryEntry(
        school_id=school.id,
        surviving_person_id=surviving,
        merged_person_id=merged,
        reason_code=PersonMergeReason.DUPLICATE_DATA_ENTRY,
        merged_by_account_id="acc_1",
        merged_at=dt.datetime(2026, 4, 1, tzinfo=dt.UTC),
    )
    db.add(entry)
    db.flush()
    return entry


def test_merge_history_records_who_and_why(db: Session) -> None:
    school = make_school(db)
    survivor, duplicate = make_person(db, given="A"), make_person(db, given="B")
    entry = _merge_entry(db, school, survivor.id, duplicate.id)
    db.commit()

    assert entry.reason_code is PersonMergeReason.DUPLICATE_DATA_ENTRY
    assert entry.merged_by_account_id == "acc_1"
    # Immutable by construction: nothing here is meant to change.
    assert not hasattr(entry, "updated_at")
    assert not hasattr(entry, "version")


def test_a_person_cannot_be_merged_into_themselves(db: Session) -> None:
    school = make_school(db)
    person = make_person(db)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO person_merge_history_entry (id, school_id, surviving_person_id, "
                "merged_person_id, reason_code, merged_by_account_id, merged_at) "
                "VALUES (:id, :s, :p, :p, 'DUPLICATE_DATA_ENTRY', 'acc', now())"
            ),
            {"id": new_id("pmh"), "s": school.id, "p": person.id},
        )
    db.rollback()


def test_merge_history_is_per_school(db: Session) -> None:
    """§3.14: H0 merge is tenant-local, so the history belongs to the school
    that performed it."""
    left, right = make_school(db, name="Leva"), make_school(db, name="Desna")
    a, b, c, d = (make_person(db, given=n) for n in "ABCD")
    _merge_entry(db, left, a.id, b.id)
    _merge_entry(db, right, c.id, d.id)
    db.commit()

    in_left = (
        db.execute(
            select(PersonMergeHistoryEntry).where(
                PersonMergeHistoryEntry.school_id == left.id
            )
        )
        .scalars()
        .all()
    )
    assert [e.merged_person_id for e in in_left] == [b.id]


def test_profiles_survive_a_round_trip(db: Session) -> None:
    school = make_school(db)
    participant = _membership(db, school, MembershipType.PARTICIPANT, name="Polaznik")
    staff = _membership(db, school, MembershipType.STAFF, name="Trener")
    profile_service.create_participant_profile(
        db,
        school_id=school.id,
        membership_id=participant.id,
        discipline_category=DisciplineCategory.MUSIC,
    )
    profile_service.create_staff_profile(
        db,
        school_id=school.id,
        membership_id=staff.id,
        specialization_codes=["PIANO"],
    )
    db.commit()
    db.expire_all()

    stored_p = db.execute(select(ParticipantProfile)).scalar_one()
    stored_s = db.execute(select(StaffProfile)).scalar_one()
    assert stored_p.discipline_category is DisciplineCategory.MUSIC
    assert stored_p.membership_type == "PARTICIPANT"
    assert stored_s.specialization_codes == ["PIANO"]
    assert stored_s.membership_type == "STAFF"
