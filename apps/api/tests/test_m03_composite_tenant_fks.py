"""M03 §7.2–7.3: the tenant travels inside the reference.

Before this, eight references between tenant tables named only the target's
`id`. Nothing in the database stopped a group in school A pointing at school
B's location — the only thing standing there was an application check, and a
check someone forgets once leaves no trace.

So every test here **bypasses the service layer**, which is where that check
lives, and writes the row itself. A test that went through the service would
only prove the service still works, which was never in doubt; what is being
proved is that the database now refuses, which is the part that keeps holding
after someone adds a new code path and forgets the check.

The parent's `UNIQUE(school_id, id)` adds no uniqueness — `id` is already the
primary key. It exists so the child's foreign key has something tenant-shaped
to point at.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.ids import new_id
from app.domains.events.models import Event
from app.domains.groups.models import Group
from app.domains.scheduling.enums import SessionSeriesFrequency
from app.domains.scheduling.models import Session as TrainingSession
from app.domains.scheduling.models import SessionSeries
from app.domains.structure.enums import LocationKind
from app.domains.structure.models import Category, Location, Program, Room
from app.platform import clock
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import make_school

#: (child table, child column, the parent it must stay inside)
RELATIONS = [
    ("structure_program", "category_id", "category"),
    ("structure_room", "location_id", "location"),
    ("group", "program_id", "program"),
    ("group", "location_id", "location"),
    ("group", "default_location_id", "location"),
    ("session", "location_id", "location"),
    ("session_series", "location_id", "location"),
    ("event", "location_id", "location"),
]


def _structure(db: Session, school_id: str) -> dict[str, str]:
    """A category, program, location and group, all belonging to `school_id`.

    The group is here because `session` and `session_series` cannot exist
    without one, and it has to be the child's *own* school's group — otherwise
    a cross-tenant test would be crossing two references at once and the
    failure would not say which constraint caught it.
    """
    category = Category(school_id=school_id, name="Kategorija")
    location = Location(school_id=school_id, name="Lokacija", kind=LocationKind.OTHER)
    group = Group(school_id=school_id, name="Grupa")
    db.add_all([category, location, group])
    db.flush()
    program = Program(school_id=school_id, category_id=category.id, name="Program")
    db.add(program)
    db.flush()
    return {
        "category": category.id,
        "program": program.id,
        "location": location.id,
        "group": group.id,
    }


def _child(
    table: str, column: str, *, school_id: str, target_id: str | None, group_id: str
) -> object:
    """A child row for `table`, with `column` pointing at `target_id`.

    Built from the mapped class rather than hand-written SQL: the point is to
    skip the service layer, not the ORM, and a hand-maintained list of NOT NULL
    columns goes stale the first time someone adds one. Every field set here is
    one the model has no default for.
    """
    now = clock.now()
    if table == "structure_program":
        return Program(school_id=school_id, name="P", category_id=target_id)
    if table == "structure_room":
        return Room(school_id=school_id, name="R", location_id=target_id)
    if table == "group":
        return Group(school_id=school_id, name="G", **{column: target_id})
    if table == "session":
        return TrainingSession(
            school_id=school_id,
            group_id=group_id,
            starts_at=now,
            ends_at=now + dt.timedelta(hours=1),
            location_id=target_id,
        )
    if table == "session_series":
        return SessionSeries(
            school_id=school_id,
            group_id=group_id,
            title="S",
            frequency=SessionSeriesFrequency.WEEKLY,
            weekdays=[0],
            start_date=now.date(),
            local_time=dt.time(10, 0),
            duration_minutes=60,
            location_id=target_id,
        )
    if table == "event":
        return Event(school_id=school_id, title="E", starts_at=now, location_id=target_id)
    raise AssertionError(f"no child builder for {table}")


@pytest.mark.parametrize("table, column, parent", RELATIONS)
def test_a_reference_cannot_cross_a_tenant(
    db: Session, table: str, column: str, parent: str
) -> None:
    """The whole point. School A's row may not name school B's structure, and
    the refusal comes from the database rather than from anyone remembering."""
    mine = make_school(db, name="Moja")
    theirs = make_school(db, name="Tudja")
    db.commit()
    own = _structure(db, mine.id)
    other = _structure(db, theirs.id)
    db.commit()

    db.add(
        _child(
            table,
            column,
            school_id=mine.id,
            target_id=other[parent],
            group_id=own["group"],
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


@pytest.mark.parametrize("table, column, parent", RELATIONS)
def test_the_same_tenant_still_works(
    db: Session, table: str, column: str, parent: str
) -> None:
    """The constraint must refuse the wrong thing without refusing the right
    one — a tenant guard that blocked legitimate references would be found
    much later, and by a user."""
    school = make_school(db, name="Jedna")
    db.commit()
    own = _structure(db, school.id)
    db.commit()

    db.add(
        _child(
            table,
            column,
            school_id=school.id,
            target_id=own[parent],
            group_id=own["group"],
        )
    )
    db.commit()


@pytest.mark.parametrize("table, column, parent", RELATIONS)
def test_a_null_reference_is_still_allowed(
    db: Session, table: str, column: str, parent: str
) -> None:
    """Postgres's default MATCH SIMPLE means a composite foreign key is simply
    not checked when any of its columns is NULL — which is the behaviour wanted
    here: no reference, nothing to verify.

    `structure_room.location_id` is the one exception, because that column is
    NOT NULL: a room with no location was never legal and this change does not
    make it so.
    """
    school = make_school(db)
    db.commit()
    own = _structure(db, school.id)
    db.commit()

    row = _child(
        table, column, school_id=school.id, target_id=None, group_id=own["group"]
    )
    db.add(row)
    if table == "structure_room":
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        return
    db.commit()


def test_deleting_a_location_nulls_only_the_reference(db: Session) -> None:
    """`ON DELETE SET NULL (location_id)` names the column deliberately: the
    plain form would try to null `school_id` too, and that column is NOT NULL.
    The row must survive with its tenant intact."""
    school = make_school(db)
    db.commit()
    own = _structure(db, school.id)
    db.commit()

    group_id = new_id("grp")
    db.add(
        Group(id=group_id, school_id=school.id, name="G", location_id=own["location"])
    )
    db.commit()

    db.execute(
        text("DELETE FROM structure_location WHERE id = :id"), {"id": own["location"]}
    )
    db.commit()

    row = db.execute(
        text('SELECT school_id, location_id FROM "group" WHERE id = :id'),
        {"id": group_id},
    ).one()
    assert row.school_id == school.id
    assert row.location_id is None


def test_deleting_a_location_still_takes_its_rooms(db: Session) -> None:
    """`structure_room` keeps CASCADE — the existing behaviour, and the
    sensible one: a room cannot outlive the place it is in."""
    school = make_school(db)
    db.commit()
    own = _structure(db, school.id)
    room = Room(school_id=school.id, location_id=own["location"], name="Sala")
    db.add(room)
    db.commit()

    db.execute(
        text("DELETE FROM structure_location WHERE id = :id"), {"id": own["location"]}
    )
    db.commit()

    # Asked of the database, not of the session: `expire_on_commit` is off, so
    # `db.get` would hand back the cached object and never notice the cascade.
    survivors = db.execute(
        text("SELECT count(*) FROM structure_room WHERE id = :id"), {"id": room.id}
    ).scalar_one()
    assert survivors == 0


def test_every_structure_parent_exposes_a_composite_target(db: Session) -> None:
    """§7.2. Without `UNIQUE(school_id, id)` on the parent, the child's foreign
    key has nothing tenant-shaped to point at — this is the constraint that
    makes the rest possible, so its absence should fail loudly."""
    present = {
        row[0]
        for row in db.execute(
            text(
                "SELECT conrelid::regclass::text FROM pg_constraint"
                " WHERE contype = 'u'"
                " AND conname LIKE '%_tenant'"
                " AND conrelid::regclass::text LIKE 'structure_%'"
            )
        ).all()
    }
    assert {"structure_category", "structure_program", "structure_location"} <= present


@pytest.mark.parametrize("table, column, parent", RELATIONS)
def test_the_composite_foreign_key_actually_exists(
    db: Session, table: str, column: str, parent: str
) -> None:
    """Names the constraint in the database, not in the model file.

    The model could declare a `ForeignKeyConstraint` that no migration ever
    applied, and every behavioural test above would still pass against a
    database that had the old single-column key — because the old key refuses
    an unknown id too. This is the test that tells those two apart.
    """
    columns = {
        row[0]
        for row in db.execute(
            text(
                "SELECT array_to_string(ARRAY("
                "  SELECT attname FROM unnest(c.conkey) k"
                "  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k"
                "), ',')"
                " FROM pg_constraint c"
                " WHERE c.contype = 'f'"
                " AND c.conrelid = cast(:table AS regclass)"
            ),
            {"table": f'"{table}"'},
        ).all()
    }
    assert f"school_id,{column}" in columns or f"{column},school_id" in columns


def test_one_delete_can_null_two_references_on_the_same_row(db: Session) -> None:
    """A group may point at the same location twice — as its location and as
    its default — and deleting that location fires both `SET NULL (column)`
    actions against the same row in one statement.

    Two referential actions on one row could have contradicted each other, so
    this is checked rather than assumed: both columns end up NULL, the row
    survives, and its tenant is untouched.
    """
    school = make_school(db)
    db.commit()
    own = _structure(db, school.id)
    group = Group(
        school_id=school.id,
        name="Grupa sa dve veze",
        location_id=own["location"],
        default_location_id=own["location"],
    )
    db.add(group)
    db.commit()

    db.execute(
        text("DELETE FROM structure_location WHERE id = :id"), {"id": own["location"]}
    )
    db.commit()

    row = db.execute(
        text(
            'SELECT school_id, location_id, default_location_id'
            ' FROM "group" WHERE id = :id'
        ),
        {"id": group.id},
    ).one()
    assert row.school_id == school.id
    assert row.location_id is None
    assert row.default_location_id is None


def test_a_school_cannot_be_deleted_out_from_under_its_security_state(
    db: Session,
) -> None:
    """`tenant_security_state.school_id` is `ON DELETE RESTRICT` on purpose
    (§5.2): the row is one-per-school and records every tenant-wide
    invalidation, so a hard delete of the school would erase the evidence
    rather than the school. Schools end through their status, not by deletion.

    This lives here because the composite keys above made every *other*
    tenant table cascade, and it would be easy to later "fix" this one for
    consistency. It is not an inconsistency.
    """
    school = make_school(db)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM school WHERE id = :id"), {"id": school.id})
        db.flush()
    db.rollback()
