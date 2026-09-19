"""M03 §7.2–7.3, second slice: the day's own rows carry their tenant too.

The first slice closed the references into the structure domain. These are the
seven that point at `group`, `session` and `session_series` — the rows a
school's day is actually made of, and the ones where a crossed reference would
do the most damage: a person enrolled into another school's group, attendance
taken for another school's session.

As in the first slice, every test here writes the row itself rather than going
through the service layer, because the service layer is where the old check
lived. What is being proved is that the database refuses.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.domains.attendance.models import AttendanceRecord
from app.domains.groups.models import Group, GroupMembership
from app.domains.progress.models import ProgressNote
from app.domains.scheduling.enums import SessionSeriesFrequency
from app.domains.scheduling.models import Session as TrainingSession
from app.domains.scheduling.models import SessionSeries
from app.platform import clock
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import make_person, make_school

#: (child table, child column, the parent kind it must stay inside)
RELATIONS = [
    ("session", "group_id", "group"),
    ("session", "series_id", "series"),
    ("session_series", "group_id", "group"),
    ("group_membership", "group_id", "group"),
    ("attendance_record", "session_id", "session"),
    ("progress_note", "group_id", "group"),
    ("progress_note", "session_id", "session"),
]


def _day(db: Session, school_id: str) -> dict[str, str]:
    """A group, a series and a session, all belonging to `school_id`."""
    now = clock.now()
    group = Group(school_id=school_id, name="Grupa")
    db.add(group)
    db.flush()
    series = SessionSeries(
        school_id=school_id,
        group_id=group.id,
        title="Serija",
        frequency=SessionSeriesFrequency.WEEKLY,
        weekdays=[0],
        start_date=now.date(),
        local_time=dt.time(10, 0),
        duration_minutes=60,
    )
    session = TrainingSession(
        school_id=school_id,
        group_id=group.id,
        starts_at=now,
        ends_at=now + dt.timedelta(hours=1),
    )
    db.add_all([series, session])
    db.flush()
    return {"group": group.id, "series": series.id, "session": session.id}


def _child(
    table: str,
    column: str,
    *,
    school_id: str,
    target_id: str | None,
    own: dict[str, str],
    person_id: str,
) -> object:
    """A child row for `table`, with `column` pointing at `target_id`.

    Every *other* reference on the row is one of the child's own school's, so a
    failure can only be the column under test. Built from the mapped class:
    the point is to skip the service layer, not the ORM.
    """
    now = clock.now()
    if table == "session":
        return TrainingSession(
            school_id=school_id,
            group_id=target_id if column == "group_id" else own["group"],
            series_id=target_id if column == "series_id" else None,
            starts_at=now,
            ends_at=now + dt.timedelta(hours=1),
        )
    if table == "session_series":
        return SessionSeries(
            school_id=school_id,
            group_id=target_id,
            title="S",
            frequency=SessionSeriesFrequency.WEEKLY,
            weekdays=[0],
            start_date=now.date(),
            local_time=dt.time(10, 0),
            duration_minutes=60,
        )
    if table == "group_membership":
        return GroupMembership(
            school_id=school_id,
            group_id=target_id,
            person_id=person_id,
            joined_at=now,
        )
    if table == "attendance_record":
        return AttendanceRecord(
            school_id=school_id, session_id=target_id, person_id=person_id
        )
    if table == "progress_note":
        return ProgressNote(
            school_id=school_id,
            person_id=person_id,
            author_person_id=person_id,
            group_id=target_id if column == "group_id" else own["group"],
            session_id=target_id if column == "session_id" else None,
            note="Beleška",
        )
    raise AssertionError(f"no child builder for {table}")


@pytest.mark.parametrize("table, column, parent", RELATIONS)
def test_a_reference_cannot_cross_a_tenant(
    db: Session, table: str, column: str, parent: str
) -> None:
    """School A's row may not name school B's group, series or session, and the
    refusal comes from the database rather than from anyone remembering."""
    mine = make_school(db, name="Moja")
    theirs = make_school(db, name="Tudja")
    person = make_person(db)
    db.commit()
    own = _day(db, mine.id)
    other = _day(db, theirs.id)
    db.commit()

    db.add(
        _child(
            table,
            column,
            school_id=mine.id,
            target_id=other[parent],
            own=own,
            person_id=person.id,
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
    one — a guard that blocked legitimate references would be found much later,
    and by a user."""
    school = make_school(db, name="Jedna")
    person = make_person(db)
    db.commit()
    own = _day(db, school.id)
    db.commit()

    db.add(
        _child(
            table,
            column,
            school_id=school.id,
            target_id=own[parent],
            own=own,
            person_id=person.id,
        )
    )
    db.commit()


@pytest.mark.parametrize("table, column, parent", RELATIONS)
def test_the_composite_foreign_key_actually_exists(
    db: Session, table: str, column: str, parent: str
) -> None:
    """Names the constraint in the database, not in the model file.

    A behavioural test alone cannot tell a composite key from the single-column
    one it replaced — both refuse an unknown id. This is the test that tells
    them apart.
    """
    columns = {
        row[0]
        for row in db.execute(
            text(
                "SELECT array_to_string(ARRAY("
                "  SELECT attname FROM unnest(c.conkey) k"
                "  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k"
                "  ORDER BY attname"
                "), ',')"
                " FROM pg_constraint c"
                " WHERE c.contype = 'f'"
                " AND c.conrelid = cast(:table AS regclass)"
            ),
            {"table": f'"{table}"'},
        ).all()
    }
    # Sorted by the query, so there is one spelling to compare against —
    # `unnest ... JOIN` on its own does not promise the array's order.
    assert ",".join(sorted(("school_id", column))) in columns


@pytest.mark.parametrize("table", ["group", "session", "session_series"])
def test_every_parent_exposes_a_composite_target(db: Session, table: str) -> None:
    """§7.2. Without `UNIQUE(school_id, id)` on the parent, the child's foreign
    key has nothing tenant-shaped to point at."""
    present = db.execute(
        text(
            "SELECT count(*) FROM pg_constraint"
            " WHERE contype = 'u' AND conrelid = cast(:table AS regclass)"
            " AND array_to_string(ARRAY("
            "   SELECT attname FROM unnest(conkey) k"
            "   JOIN pg_attribute a ON a.attrelid = conrelid AND a.attnum = k"
            " ), ',') IN ('school_id,id', 'id,school_id')"
        ),
        {"table": f'"{table}"'},
    ).scalar_one()
    assert present == 1


def test_deleting_a_series_keeps_its_sessions(db: Session) -> None:
    """`ON DELETE SET NULL (series_id)` names the column, because the plain
    form would try to null `school_id` and that column is NOT NULL.

    Deleting a recurring template must not delete the sessions it already
    generated — those are history, and a school's past is not a template.
    """
    school = make_school(db)
    db.commit()
    own = _day(db, school.id)
    session = db.get(TrainingSession, own["session"])
    assert session is not None
    session.series_id = own["series"]
    db.commit()

    db.execute(
        text("DELETE FROM session_series WHERE id = :id"), {"id": own["series"]}
    )
    db.commit()

    row = db.execute(
        text("SELECT school_id, series_id FROM session WHERE id = :id"),
        {"id": own["session"]},
    ).one()
    assert row.school_id == school.id
    assert row.series_id is None


def test_deleting_a_group_takes_its_roster_and_its_sessions(db: Session) -> None:
    """CASCADE is kept on the five NOT NULL references: a membership, a session
    or a series without its group is not a record, it is a fragment."""
    school = make_school(db)
    person = make_person(db)
    db.commit()
    own = _day(db, school.id)
    db.add(
        GroupMembership(
            school_id=school.id,
            group_id=own["group"],
            person_id=person.id,
            joined_at=clock.now(),
        )
    )
    db.commit()

    db.execute(text('DELETE FROM "group" WHERE id = :id'), {"id": own["group"]})
    db.commit()

    for table in ("group_membership", "session", "session_series"):
        left = db.execute(
            text(f"SELECT count(*) FROM {table} WHERE school_id = :id"),
            {"id": school.id},
        ).scalar_one()
        assert left == 0, f"{table} outlived its group"
