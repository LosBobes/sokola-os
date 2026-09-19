"""Creating and updating the activity profiles (M06 §2.5–2.6, §3.6).

§3.6 requires a profile to belong to the same school as its membership *and* to
match its type, at create and at update. The composite foreign key enforces the
first two; this module refuses the third early, so a caller gets
``M06_PROFILE_TYPE_MISMATCH``-shaped feedback rather than a constraint violation
surfacing as a 500.

``specialization_codes`` is sorted and deduplicated on write (§2.6). Two
profiles listing the same specializations in different orders are the same
profile, and storing them differently means every comparison and every diff has
to re-sort before it can tell.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import BadRequestError, ConflictError, NotFoundError
from app.domains.people.activity_profiles import (
    MAX_SPECIALIZATION_CODES,
    ParticipantProfile,
    StaffProfile,
)
from app.domains.school.enums import MembershipType
from app.domains.school.models import SchoolMembership


def _require_membership(
    db: Session, school_id: str, membership_id: str, expected: MembershipType
) -> SchoolMembership:
    membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.id == membership_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        # Safe-not-found (§4): a membership in another school reads exactly like
        # one that does not exist, so the caller learns nothing either way.
        raise NotFoundError("Članstvo nije pronađeno.")
    if membership.membership_type is not expected:
        raise ConflictError(
            f"Profil zahteva članstvo tipa {expected.value}, "
            f"a ovo je {membership.membership_type.value}."
        )
    return membership


def normalize_specialization_codes(codes: list[str] | None) -> list[str] | None:
    """Sort and deduplicate (§2.6), refusing more than the cap allows."""
    if codes is None:
        return None
    cleaned = sorted({code.strip() for code in codes if code and code.strip()})
    if len(cleaned) > MAX_SPECIALIZATION_CODES:
        raise BadRequestError(
            f"Najviše {MAX_SPECIALIZATION_CODES} oznaka specijalnosti."
        )
    if any(len(code) > 64 for code in cleaned):
        raise BadRequestError("Oznaka specijalnosti ima najviše 64 znaka.")
    return cleaned or None


def create_participant_profile(
    db: Session, *, school_id: str, membership_id: str, **fields: object
) -> ParticipantProfile:
    _require_membership(db, school_id, membership_id, MembershipType.PARTICIPANT)
    if get_participant_profile(db, school_id, membership_id) is not None:
        raise ConflictError("Profil polaznika za ovo članstvo već postoji.")

    profile = ParticipantProfile(
        school_id=school_id,
        school_membership_id=membership_id,
        **fields,
    )
    db.add(profile)
    db.flush()
    return profile


def create_staff_profile(
    db: Session,
    *,
    school_id: str,
    membership_id: str,
    specialization_codes: list[str] | None = None,
    **fields: object,
) -> StaffProfile:
    _require_membership(db, school_id, membership_id, MembershipType.STAFF)
    if get_staff_profile(db, school_id, membership_id) is not None:
        raise ConflictError("Profil osoblja za ovo članstvo već postoji.")

    profile = StaffProfile(
        school_id=school_id,
        school_membership_id=membership_id,
        specialization_codes=normalize_specialization_codes(specialization_codes),
        **fields,
    )
    db.add(profile)
    db.flush()
    return profile


def get_participant_profile(
    db: Session, school_id: str, membership_id: str
) -> ParticipantProfile | None:
    return db.execute(
        select(ParticipantProfile).where(
            ParticipantProfile.school_id == school_id,
            ParticipantProfile.school_membership_id == membership_id,
        )
    ).scalar_one_or_none()


def get_staff_profile(
    db: Session, school_id: str, membership_id: str
) -> StaffProfile | None:
    return db.execute(
        select(StaffProfile).where(
            StaffProfile.school_id == school_id,
            StaffProfile.school_membership_id == membership_id,
        )
    ).scalar_one_or_none()
