"""M06 §2.1 and §2.4: a person's protected contact, and one school's view of them.

The rule these tests exist to pin down is §3.4: a matching email or phone is a
**candidate flag and nothing more**. Two real people share a family address, and
a system that treats the match as identity has destroyed one person's records to
save an operator a click. So the blind-index columns are indexed and not unique,
and nothing here auto-links or auto-merges.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.ids import new_id
from app.domains.identity.enums import PersonDedupeStatus
from app.domains.identity.models import Person
from app.domains.people.profile_models import (
    SchoolPersonProfile,
    normalize_local_person_code,
)
from app.domains.school import ownership
from app.domains.school.ownership_enums import OwnerNominationKind
from app.platform import crypto
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import (
    add_membership,
    ensure_person_profile,
    make_person,
    make_school,
)

EMAIL = "porodica@example.invalid"


def _with_contact(db: Session, person: Person, email: str) -> Person:
    """Store a contact the way a real command would: encrypt, then blind-index."""
    canonical = crypto.canonical_email(email)
    person.email_ciphertext = crypto.encrypt_contact(
        canonical, context=f"person/{person.id}/email"
    )
    digest, version = crypto.fingerprint(canonical)
    person.email_blind_index = digest
    person.email_blind_index_key_version = version
    db.flush()
    return person


# ---------------------------------------------------------------------------
# Person contact (§2.1, §3.4)
# ---------------------------------------------------------------------------


def test_a_contact_round_trips_and_is_not_stored_in_clear(db: Session) -> None:
    person = make_person(db, given="Ana", family="Marković")
    _with_contact(db, person, EMAIL)
    db.commit()

    stored = db.execute(
        text("SELECT email_ciphertext, email_blind_index FROM person WHERE id = :id"),
        {"id": person.id},
    ).one()
    assert EMAIL not in stored.email_ciphertext
    assert EMAIL not in stored.email_blind_index
    assert (
        crypto.decrypt_contact(stored.email_ciphertext, context=f"person/{person.id}/email")
        == EMAIL
    )


def test_two_people_may_share_a_contact_and_stay_two_people(db: Session) -> None:
    """§3.4 and §3.1: a shared family address is a candidate flag, never a link.

    If the blind index were unique, the second person could not be created at
    all — which is the failure this test exists to prevent from being
    'optimized' in later.
    """
    mother = _with_contact(db, make_person(db, given="Jelena", family="Marković"), EMAIL)
    child = _with_contact(db, make_person(db, given="Ana", family="Marković"), EMAIL)
    child.dedupe_status = PersonDedupeStatus.POTENTIAL_DUPLICATE
    db.commit()

    assert mother.id != child.id
    assert mother.email_blind_index == child.email_blind_index

    # The index finds both, which is exactly what a candidate lookup wants.
    candidates = (
        db.execute(
            select(Person).where(Person.email_blind_index == mother.email_blind_index)
        )
        .scalars()
        .all()
    )
    assert {p.id for p in candidates} == {mother.id, child.id}
    assert mother.dedupe_status is PersonDedupeStatus.CLEAR


def test_a_ciphertext_and_its_blind_index_must_travel_together(db: Session) -> None:
    """One without the other is a silent failure: a contact nobody can
    deduplicate, or an index pointing at nothing."""
    person = _with_contact(db, make_person(db), EMAIL)
    db.commit()

    for column in ("email_ciphertext", "email_blind_index"):
        with pytest.raises(IntegrityError):
            db.execute(
                text(f"UPDATE person SET {column} = NULL WHERE id = :id"), {"id": person.id}
            )
        db.rollback()


def test_a_persons_contact_cannot_be_moved_to_another_person(db: Session) -> None:
    """The AEAD context binds the ciphertext to the row, so a copied contact
    column fails to decrypt rather than reading back as that person's."""
    owner = _with_contact(db, make_person(db, given="Ana", family="Prva"), EMAIL)
    other = make_person(db, given="Marko", family="Drugi")
    db.commit()

    with pytest.raises(crypto.ContactCryptoError):
        crypto.decrypt_contact(
            owner.email_ciphertext, context=f"person/{other.id}/email"
        )


def test_merged_is_the_only_status_that_names_a_survivor(db: Session) -> None:
    survivor, duplicate = make_person(db, given="Ana"), make_person(db, given="Ana")
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE person SET merged_into_person_id = :s WHERE id = :d"),
            {"s": survivor.id, "d": duplicate.id},
        )
    db.rollback()

    db.execute(
        text(
            "UPDATE person SET dedupe_status = 'MERGED', merged_into_person_id = :s "
            "WHERE id = :d"
        ),
        {"s": survivor.id, "d": duplicate.id},
    )
    db.commit()
    db.expire_all()
    assert db.get(Person, duplicate.id).merged_into_person_id == survivor.id  # type: ignore[union-attr]


def test_a_person_cannot_be_merged_into_themselves(db: Session) -> None:
    person = make_person(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE person SET dedupe_status = 'MERGED', merged_into_person_id = id "
                "WHERE id = :id"
            ),
            {"id": person.id},
        )
    db.rollback()


def test_an_unknown_birth_date_is_allowed_and_means_unproven(db: Session) -> None:
    """§2.1: unknown is a legitimate value. §3.1 turns it into NOT_ELIGIBLE at
    the account-eligibility guard rather than into a guess about someone's age."""
    person = make_person(db)
    assert person.birth_date is None

    person.birth_date = dt.date(2015, 3, 14)
    db.commit()
    db.expire_all()
    assert db.get(Person, person.id).birth_date == dt.date(2015, 3, 14)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# SchoolPersonProfile (§2.4)
# ---------------------------------------------------------------------------


def test_a_membership_makes_the_school_know_the_person_once(db: Session) -> None:
    school = make_school(db)
    person = make_person(db)
    add_membership(db, person=person, school=school)
    db.commit()

    profiles = (
        db.execute(
            select(SchoolPersonProfile).where(SchoolPersonProfile.school_id == school.id)
        )
        .scalars()
        .all()
    )
    assert [p.person_id for p in profiles] == [person.id]

    # A second membership type for the same person does not make a second
    # profile: a school knows a person once, however many hats they wear.
    ensure_person_profile(db, school=school, person=person)
    db.commit()
    assert (
        db.execute(
            select(SchoolPersonProfile).where(SchoolPersonProfile.school_id == school.id)
        )
        .scalars()
        .all()
        .__len__()
        == 1
    )


def test_the_database_refuses_two_profiles_for_one_person_in_one_school(
    db: Session,
) -> None:
    school, person = make_school(db), make_person(db)
    ensure_person_profile(db, school=school, person=person)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_person_profile (id, school_id, person_id, version, "
                "created_at, updated_at) VALUES (:id, :s, :p, 1, now(), now())"
            ),
            {"id": new_id("spp"), "s": school.id, "p": person.id},
        )
    db.rollback()


def test_the_same_person_is_known_separately_by_two_schools(db: Session) -> None:
    """§3.2: nothing about one school's view carries into another's."""
    left, right = make_school(db, name="Prva"), make_school(db, name="Druga")
    person = make_person(db)
    a = ensure_person_profile(db, school=left, person=person)
    b = ensure_person_profile(db, school=right, person=person)
    db.commit()

    assert a.id != b.id
    a.local_person_code = "001"
    a.normalized_local_person_code = "001"
    db.commit()
    db.expire_all()
    assert db.get(SchoolPersonProfile, b.id).local_person_code is None  # type: ignore[union-attr]


def test_a_local_code_is_unique_within_a_school_and_free_in_another(db: Session) -> None:
    left, right = make_school(db, name="Prva"), make_school(db, name="Druga")
    first = ensure_person_profile(db, school=left, person=make_person(db, given="A"))
    second = ensure_person_profile(db, school=left, person=make_person(db, given="B"))
    elsewhere = ensure_person_profile(db, school=right, person=make_person(db, given="C"))
    for profile in (first, elsewhere):
        profile.local_person_code = "UC-1"
        profile.normalized_local_person_code = "UC-1"
    db.commit()

    second.local_person_code = "UC-1"
    second.normalized_local_person_code = "UC-1"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_profiles_without_a_code_do_not_collide(db: Session) -> None:
    """The uniqueness is partial for a reason: most people have no local code,
    and NULLs must not be treated as a shared value."""
    school = make_school(db)
    for name in ("A", "B", "C"):
        ensure_person_profile(db, school=school, person=make_person(db, given=name))
    db.commit()

    codes = (
        db.execute(
            select(SchoolPersonProfile.normalized_local_person_code).where(
                SchoolPersonProfile.school_id == school.id
            )
        )
        .scalars()
        .all()
    )
    assert codes == [None, None, None]


def test_a_code_is_normalized_but_never_case_folded(db: Session) -> None:
    """§2.4: NFKC plus an outer trim, no casefold, because M20's external
    reference contract is case-sensitive — folding would merge two pupils."""
    assert normalize_local_person_code("  AB-1  ") == "AB-1"
    assert normalize_local_person_code("ｱ") == "ア"  # NFKC compatibility form
    assert normalize_local_person_code("AB-1") != normalize_local_person_code("ab-1")


@pytest.mark.parametrize("bad", ["a​b", "a­b", "a\u0000b", "", " ", "x" * 65])
def test_an_unusable_code_is_refused(bad: str) -> None:
    """Invisible characters are refused because they are invisible: two codes
    that look identical on screen would both be stored and be untellable apart."""
    with pytest.raises(ValueError):
        normalize_local_person_code(bad)


def test_a_code_and_its_normal_form_must_travel_together(db: Session) -> None:
    school, person = make_school(db), make_person(db)
    profile = ensure_person_profile(db, school=school, person=person)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE school_person_profile SET local_person_code = 'X' WHERE id = :id"
            ),
            {"id": profile.id},
        )
    db.rollback()


# ---------------------------------------------------------------------------
# F-14: M04's owner nomination now references the profile
# ---------------------------------------------------------------------------


def test_a_nomination_references_the_profile_not_the_membership(db: Session) -> None:
    school, person = make_school(db), make_person(db)
    add_membership(db, person=person, school=school)
    profile = ensure_person_profile(db, school=school, person=person)

    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.commit()
    assert nomination.target_school_person_profile_id == profile.id


def test_a_nomination_cannot_reference_another_schools_profile(db: Session) -> None:
    """The composite FK still names the tenant, so moving the reference from
    membership to profile did not weaken the guarantee for an instant."""
    left, right = make_school(db, name="Leva"), make_school(db, name="Desna")
    person = make_person(db)
    foreign = ensure_person_profile(db, school=right, person=person)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_owner_nomination (id, school_id, target_person_id, "
                "target_school_person_profile_id, kind, status, created_by_actor_ref, "
                "version, created_at, updated_at) VALUES (:id, :s, :p, :prof, "
                "'ADDITIONAL_OWNER', 'PENDING', 'x', 1, now(), now())"
            ),
            {"id": new_id("nom"), "s": left.id, "p": person.id, "prof": foreign.id},
        )
    db.rollback()


def test_a_person_the_school_does_not_know_cannot_be_nominated(db: Session) -> None:
    from app.common.errors import NotFoundError

    school = make_school(db)
    stranger = make_person(db, given="Spoljni", family="Čovek")

    with pytest.raises(NotFoundError):
        ownership.nominate_owner(
            db,
            school_id=school.id,
            person_id=stranger.id,
            kind=OwnerNominationKind.ADDITIONAL_OWNER,
            actor_ref="owner",
        )
