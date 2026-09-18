"""M04 §2.1–2.5: the school anchor.

Each test here drives an invariant the contract states, and the ones that matter
most are the ones asserting a write is *refused*: an organization link, a locator
and a status history are all "append the next one" structures, and the failure
mode is never a visible error — it is a second current row that nothing notices
until a bill is issued against the wrong organization.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import AppError, ConflictError
from app.common.ids import new_id
from app.domains.organization.enums import (
    OrganizationSchoolChangeReason,
    OrganizationStatus,
)
from app.domains.organization.models import Organization
from app.domains.school import anchor
from app.domains.school.enums import (
    LocatorKind,
    LocatorStatus,
    SchoolStatus,
    SchoolStatusReason,
)
from app.domains.school.models import School, SchoolLocator, SchoolStatusTransition
from app.platform import clock
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import make_school


def _organization(db: Session, name: str = "Sokolić d.o.o.") -> Organization:
    org = Organization(
        organization_ref=new_id("oref"),
        legal_name=name,
        country_code="RS",
        created_by_actor_ref="platform",
        updated_by_actor_ref="platform",
    )
    db.add(org)
    db.flush()
    return org


# ---------------------------------------------------------------------------
# What a school looks like the moment it exists
# ---------------------------------------------------------------------------


def test_a_new_school_has_a_complete_anchor(db: Session) -> None:
    school = make_school(db)

    link = anchor.current_organization_link(db, school.id)
    assert link is not None
    assert link.valid_to is None
    assert link.change_reason_code is OrganizationSchoolChangeReason.INITIAL_PROVISIONING

    assert anchor.active_locator(db, school.id, LocatorKind.SLUG) is not None
    code = anchor.active_locator(db, school.id, LocatorKind.SCHOOL_CODE)
    assert code is not None and len(code.normalized_value) == 8

    history = anchor.status_history(db, school.id)
    assert [t.sequence_no for t in history] == [1]
    assert history[0].from_status is None
    assert history[0].reason_code is SchoolStatusReason.SCHOOL_CREATED


def test_the_signup_endpoint_produces_the_same_anchor(client, db: Session) -> None:
    """The HTTP path, not just the factory: a school created by a real request
    must be as complete as one created by a test helper."""
    from app.security.auth import DEV_PERSON_HEADER

    from tests.factories import make_person

    person = make_person(db, given="Vlada", family="Nikolić")
    response = client.post(
        "/schools",
        json={"name": "Nova škola", "type": "SCHOOL"},
        headers={DEV_PERSON_HEADER: person.id},
    )
    assert response.status_code in (200, 201), response.text
    school_id = response.json()["id"]

    assert anchor.current_organization_link(db, school_id) is not None
    assert anchor.active_locator(db, school_id, LocatorKind.SLUG) is not None
    assert anchor.active_locator(db, school_id, LocatorKind.SCHOOL_CODE) is not None
    assert len(anchor.status_history(db, school_id)) == 1
    assert response.json()["status"] == "IN_PREPARATION"


# ---------------------------------------------------------------------------
# Organization link (§2.3, §3.1)
# ---------------------------------------------------------------------------


def test_a_school_cannot_hold_two_current_organization_links(db: Session) -> None:
    school = make_school(db)
    with pytest.raises(ConflictError):
        anchor.open_organization_link(
            db,
            school_id=school.id,
            organization=_organization(db),
            reason=OrganizationSchoolChangeReason.INITIAL_PROVISIONING,
            case_reference="CASE-1",
            actor_ref="platform",
        )


def test_the_database_refuses_a_second_current_link_even_around_the_service(
    db: Session,
) -> None:
    """The service check is a nicety; this index is the actual guarantee."""
    school = make_school(db)
    holder = _organization(db)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO organization_school (id, organization_id, school_id, valid_from, "
                "change_reason_code, case_reference, created_by_actor_ref, created_at) "
                "VALUES (:id, :org, :school, now(), 'INITIAL_PROVISIONING', 'X', 'x', now())"
            ),
            {"id": new_id("oslk"), "org": holder.id, "school": school.id},
        )
    db.rollback()


def test_a_transfer_closes_the_old_link_at_the_instant_the_new_one_opens(
    db: Session,
) -> None:
    """Half-open intervals meeting exactly: no gap where the school belonged to
    nobody, and no overlap where it belonged to two organizations."""
    school = make_school(db)
    first = anchor.current_organization_link(db, school.id)
    assert first is not None
    successor = _organization(db, "Novi holder d.o.o.")

    second = anchor.transfer_organization(
        db,
        school_id=school.id,
        organization=successor,
        reason=OrganizationSchoolChangeReason.LEGAL_OWNERSHIP_TRANSFER,
        case_reference="CASE-77",
        actor_ref="platform",
    )
    db.flush()

    assert first.valid_to is not None
    assert first.valid_to == second.valid_from
    assert second.valid_to is None
    assert anchor.current_organization_link(db, school.id) is second
    # Nothing was deleted: the school's history still names its first holder.
    links = db.execute(
        select(anchor.OrganizationSchool).where(
            anchor.OrganizationSchool.school_id == school.id
        )
    ).scalars().all()
    assert len(links) == 2


def test_a_transfer_may_not_reuse_the_initial_provisioning_reason(db: Session) -> None:
    school = make_school(db)
    with pytest.raises(ConflictError):
        anchor.transfer_organization(
            db,
            school_id=school.id,
            organization=_organization(db, "Drugi"),
            reason=OrganizationSchoolChangeReason.INITIAL_PROVISIONING,
            case_reference="CASE-1",
            actor_ref="platform",
        )


def test_an_archived_organization_cannot_receive_a_school(db: Session) -> None:
    school = make_school(db)
    archived = _organization(db, "Ugašena d.o.o.")
    archived.status = OrganizationStatus.ARCHIVED
    db.flush()

    with pytest.raises(ConflictError):
        anchor.transfer_organization(
            db,
            school_id=school.id,
            organization=archived,
            reason=OrganizationSchoolChangeReason.CORPORATE_RESTRUCTURE,
            case_reference="CASE-2",
            actor_ref="platform",
        )


def test_transferring_to_the_same_organization_is_refused(db: Session) -> None:
    school = make_school(db)
    link = anchor.current_organization_link(db, school.id)
    assert link is not None
    holder = db.get(Organization, link.organization_id)
    assert holder is not None

    with pytest.raises(ConflictError):
        anchor.transfer_organization(
            db,
            school_id=school.id,
            organization=holder,
            reason=OrganizationSchoolChangeReason.CORPORATE_RESTRUCTURE,
            case_reference="CASE-3",
            actor_ref="platform",
        )


def test_an_organization_link_is_not_access(db: Session) -> None:
    """§3.1.2. Two schools under one organization stay two tenants. This asserts
    the shape of the data rather than a query, because the guarantee is that no
    query is ever written against this link — there is nothing to join through."""
    holder = _organization(db, "Grupa d.o.o.")
    left, right = make_school(db, name="Škola A"), make_school(db, name="Škola B")
    for school in (left, right):
        current = anchor.current_organization_link(db, school.id)
        assert current is not None
        current.valid_to = clock.now()
        db.flush()
        anchor.open_organization_link(
            db,
            school_id=school.id,
            organization=holder,
            reason=OrganizationSchoolChangeReason.INITIAL_PROVISIONING,
            case_reference="CASE-G",
            actor_ref="platform",
        )
    db.flush()

    # The link carries no role, permission or membership column to be mistaken
    # for a grant, which is the point.
    link = anchor.current_organization_link(db, left.id)
    assert link is not None
    assert not hasattr(link, "role_code")
    assert not hasattr(link, "person_id")


# ---------------------------------------------------------------------------
# Locators (§2.4, §3.7)
# ---------------------------------------------------------------------------


def test_two_schools_cannot_hold_the_same_active_slug(db: Session) -> None:
    first, second = make_school(db, name="Prva"), make_school(db, name="Druga")
    slug = anchor.active_locator(db, first.id, LocatorKind.SLUG)
    assert slug is not None

    anchor.rotate_locator(
        db, school_id=second.id, kind=LocatorKind.SLUG, value="privremeno", actor_ref="t"
    )
    with pytest.raises(ConflictError):
        anchor.rotate_locator(
            db,
            school_id=second.id,
            kind=LocatorKind.SLUG,
            value=slug.normalized_value,
            actor_ref="t",
        )


def test_rotating_a_slug_retires_the_old_one_and_links_it_forward(db: Session) -> None:
    school = make_school(db)
    old = anchor.active_locator(db, school.id, LocatorKind.SLUG)
    assert old is not None

    new = anchor.rotate_locator(
        db, school_id=school.id, kind=LocatorKind.SLUG, value="Škola Sokolić", actor_ref="t"
    )
    db.flush()

    assert new.normalized_value == "skola-sokolic"
    assert old.status is LocatorStatus.RETIRED
    assert old.retired_at is not None and old.retired_at > old.valid_from
    assert old.replaced_by_locator_id == new.id
    # Still exactly one active of this kind.
    assert anchor.active_locator(db, school.id, LocatorKind.SLUG) is new


def test_a_retired_locator_no_longer_resolves(db: Session) -> None:
    """§3.7.3: an old URL must not reach protected content, so resolution has to
    stop at the locator rather than fall through to the school."""
    school = make_school(db)
    old = anchor.active_locator(db, school.id, LocatorKind.SLUG)
    assert old is not None
    old_value = old.normalized_value

    anchor.rotate_locator(
        db, school_id=school.id, kind=LocatorKind.SLUG, value="novo-ime", actor_ref="t"
    )
    db.flush()

    assert anchor.resolve_locator(db, LocatorKind.SLUG, old_value) is None
    assert anchor.resolve_locator(db, LocatorKind.SLUG, "novo-ime") == school.id


def test_a_freed_slug_can_be_taken_by_another_school(db: Session) -> None:
    """A retired value is history, not a reservation: it must not lock the name
    out of use forever."""
    first, second = make_school(db, name="Prva"), make_school(db, name="Druga")
    anchor.rotate_locator(
        db, school_id=first.id, kind=LocatorKind.SLUG, value="sporni-naziv", actor_ref="t"
    )
    anchor.rotate_locator(
        db, school_id=first.id, kind=LocatorKind.SLUG, value="prva-skola", actor_ref="t"
    )
    db.flush()

    taken = anchor.rotate_locator(
        db, school_id=second.id, kind=LocatorKind.SLUG, value="sporni-naziv", actor_ref="t"
    )
    db.flush()
    assert anchor.resolve_locator(db, LocatorKind.SLUG, "sporni-naziv") == second.id
    assert taken.school_id == second.id


def test_the_database_refuses_a_second_active_locator_of_a_kind(db: Session) -> None:
    school = make_school(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_locator (id, school_id, kind, normalized_value, status, "
                "valid_from, created_by_actor_ref, version) "
                "VALUES (:id, :school, 'SLUG', 'drugi-slug', 'ACTIVE', now(), 'x', 1)"
            ),
            {"id": new_id("loc"), "school": school.id},
        )
    db.rollback()


def test_a_school_code_is_read_back_the_way_people_type_it(db: Session) -> None:
    """The alphabet excludes 0/O/1/I/L precisely so this mapping is safe; a code
    is entered by a human reading it off a screen, and nowhere else."""
    school = make_school(db)
    code = anchor.active_locator(db, school.id, LocatorKind.SCHOOL_CODE)
    assert code is not None
    value = code.normalized_value

    for typed in (value.lower(), f" {value} ", "-".join([value[:4], value[4:]])):
        assert anchor.resolve_locator(db, LocatorKind.SCHOOL_CODE, typed) == school.id


def test_a_value_that_cannot_be_normalized_is_refused_rather_than_stored(
    db: Session,
) -> None:
    """Only length is unfixable. Stray punctuation, casing and diacritics are
    *normalized*, because rejecting "Škola Sokolić!" as a name would be refusing
    the input the person actually has."""
    school = make_school(db)
    for bad in ("ab", "x" * 64, "!!!"):
        with pytest.raises(AppError):
            anchor.rotate_locator(
                db, school_id=school.id, kind=LocatorKind.SLUG, value=bad, actor_ref="t"
            )

    cleaned = anchor.rotate_locator(
        db, school_id=school.id, kind=LocatorKind.SLUG, value="  -Loše--Ime-  ", actor_ref="t"
    )
    assert cleaned.normalized_value == "lose-ime"


# ---------------------------------------------------------------------------
# Status history (§2.5, §5.2)
# ---------------------------------------------------------------------------


def _activate(db: Session, school: School) -> SchoolStatusTransition:
    return anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.ACTIVE,
        reason_code=SchoolStatusReason.INITIAL_ACTIVATION,
        actor_ref="owner",
        correlation_id=new_id("corr"),
    )


def test_status_is_the_projection_of_an_appended_history(db: Session) -> None:
    school = make_school(db, status=SchoolStatus.IN_PREPARATION)
    _activate(db, school)
    db.flush()

    history = anchor.status_history(db, school.id)
    assert [(t.sequence_no, t.from_status, t.to_status) for t in history] == [
        (1, None, SchoolStatus.IN_PREPARATION),
        (2, SchoolStatus.IN_PREPARATION, SchoolStatus.ACTIVE),
    ]
    assert school.status is SchoolStatus.ACTIVE
    assert school.activated_at is not None
    assert school.version == 2


def test_a_forbidden_transition_is_refused(db: Session) -> None:
    """§5.2 lists three transitions. In particular an unfinished school is
    cancelled, never "deactivated", and a deactivated one never goes back to
    being unfinished."""
    school = make_school(db, status=SchoolStatus.IN_PREPARATION)
    with pytest.raises(ConflictError, match="nije dozvoljen"):
        anchor.transition_status(
            db,
            school=school,
            to_status=SchoolStatus.DEACTIVATED,
            reason_code=SchoolStatusReason.OPERATIONAL_PAUSE,
            actor_ref="platform",
            correlation_id=new_id("corr"),
        )
    db.rollback()

    school = db.get(School, school.id)  # type: ignore[assignment]
    assert school.status is SchoolStatus.IN_PREPARATION
    assert len(anchor.status_history(db, school.id)) == 1


def test_reactivation_never_rewrites_the_first_activation(db: Session) -> None:
    """``activated_at`` answers "has this school ever operated", which a later
    pause and resume does not change."""
    school = make_school(db, status=SchoolStatus.IN_PREPARATION)
    with clock.frozen_at("2026-01-10T08:00:00+00:00"):
        _activate(db, school)
    first_activation = school.activated_at
    assert first_activation == dt.datetime(2026, 1, 10, 8, 0, tzinfo=dt.UTC)

    with clock.frozen_at("2026-03-01T08:00:00+00:00"):
        anchor.transition_status(
            db,
            school=school,
            to_status=SchoolStatus.DEACTIVATED,
            reason_code=SchoolStatusReason.PILOT_PAUSED,
            reason_note="Pauza pilota.",
            actor_ref="platform",
            correlation_id=new_id("corr"),
        )
    assert school.deactivated_at == dt.datetime(2026, 3, 1, 8, 0, tzinfo=dt.UTC)

    with clock.frozen_at("2026-05-01T08:00:00+00:00"):
        anchor.transition_status(
            db,
            school=school,
            to_status=SchoolStatus.ACTIVE,
            reason_code=SchoolStatusReason.PILOT_RESUMED,
            reason_note="Nastavak pilota.",
            actor_ref="platform",
            correlation_id=new_id("corr"),
        )

    assert school.activated_at == first_activation
    assert school.deactivated_at is None
    assert [t.sequence_no for t in anchor.status_history(db, school.id)] == [1, 2, 3, 4]


def test_the_database_refuses_a_duplicate_sequence_number(db: Session) -> None:
    """A "replacement" transition silently reusing a sequence number is exactly
    how a status history stops being evidence."""
    school = make_school(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_status_transition (id, school_id, sequence_no, from_status, "
                "to_status, effective_at, reason_code, actor_ref, correlation_id, created_at) "
                "VALUES (:id, :school, 1, NULL, 'ACTIVE', now(), 'SCHOOL_CREATED', 'x', 'c', now())"
            ),
            {"id": new_id("sct"), "school": school.id},
        )
    db.rollback()


def test_only_the_first_transition_may_have_no_predecessor(db: Session) -> None:
    school = make_school(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_status_transition (id, school_id, sequence_no, from_status, "
                "to_status, effective_at, reason_code, actor_ref, correlation_id, created_at) "
                "VALUES (:id, :school, 2, NULL, 'ACTIVE', now(), 'INITIAL_ACTIVATION', "
                "'x', 'c', now())"
            ),
            {"id": new_id("sct"), "school": school.id},
        )
    db.rollback()


def test_transitioning_to_the_current_status_is_refused(db: Session) -> None:
    school = make_school(db)
    with pytest.raises(ConflictError, match="već u statusu"):
        _activate(db, school)


# ---------------------------------------------------------------------------
# The §2.2 CHECK contracts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("currency", "'EUR'"),
        ("country_code", "'HR'"),
        ("version", "0"),
        ("short_name", "'   '"),
    ],
)
def test_the_database_rejects_an_unsupported_school_value(
    db: Session, column: str, value: str
) -> None:
    """§3.3.5: another currency is not silently converted, it is not storable."""
    school = make_school(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text(f"UPDATE school SET {column} = {value} WHERE id = :id"), {"id": school.id}
        )
    db.rollback()


def test_other_kind_requires_a_label_and_a_named_kind_forbids_one(db: Session) -> None:
    school = make_school(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE school SET school_kind = 'OTHER', school_kind_other_label = NULL "
                 "WHERE id = :id"),
            {"id": school.id},
        )
    db.rollback()

    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE school SET school_kind = 'MUSIC_SCHOOL', "
                 "school_kind_other_label = 'nešto' WHERE id = :id"),
            {"id": school.id},
        )
    db.rollback()


def test_deactivated_and_deactivated_at_cannot_disagree(db: Session) -> None:
    school = make_school(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE school SET status = 'DEACTIVATED' WHERE id = :id"), {"id": school.id}
        )
    db.rollback()


def test_a_provisioning_reference_is_unique(db: Session) -> None:
    first, second = make_school(db, name="Prva"), make_school(db, name="Druga")
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE school SET provisioning_reference = :ref WHERE id = :id"),
            {"ref": first.provisioning_reference, "id": second.id},
        )
    db.rollback()


def test_a_locator_row_survives_its_school_being_read_back(db: Session) -> None:
    """Sanity: the ORM mapping and the migration agree on every column, which is
    the thing a hand-written migration most often gets subtly wrong."""
    school = make_school(db)
    db.commit()
    db.expire_all()

    rows = db.execute(
        select(SchoolLocator).where(SchoolLocator.school_id == school.id)
    ).scalars().all()
    assert {r.kind for r in rows} == {LocatorKind.SLUG, LocatorKind.SCHOOL_CODE}
    assert all(r.version == 1 and r.retired_at is None for r in rows)
