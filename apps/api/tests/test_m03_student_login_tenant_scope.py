"""M03 §4.4–4.5, F-27: "may this child sign in" belongs to one school.

`student_login_authorization` used to be globally unique on
`student_person_id` — one row per child, for all of SOKOLA. That made the
first school to decide the only school that could: a child in school A and
school B had one authorization between them, and neither school could see or
change what the other had set.

The child stays global. §7.5 is explicit that a global table gets no false
`school_id`, and a person is the same person everywhere. What is tenant-scoped
is the *decision*, which is what these tests are about.
"""

from __future__ import annotations

import pytest
from app.domains.identity.models import StudentLoginAuthorization
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import make_person, make_school


def test_two_schools_decide_independently_for_the_same_child(db: Session) -> None:
    """The finding, made concrete. One child trains at two schools; each school
    holds its own answer, and they may differ."""
    child = make_person(db, given="Mila", family="Jovanović")
    first = make_school(db, name="Prva")
    second = make_school(db, name="Druga")
    db.commit()

    db.add_all([
        StudentLoginAuthorization(
            school_id=first.id, student_person_id=child.id, login_enabled=True
        ),
        StudentLoginAuthorization(
            school_id=second.id, student_person_id=child.id, login_enabled=False
        ),
    ])
    db.commit()

    rows = db.execute(
        text(
            "SELECT school_id, login_enabled FROM student_login_authorization"
            " WHERE student_person_id = :p ORDER BY school_id"
        ),
        {"p": child.id},
    ).all()
    assert len(rows) == 2
    assert {r.login_enabled for r in rows} == {True, False}


def test_one_school_holds_one_decision_per_child(db: Session) -> None:
    """Independent per school, but still exactly one answer within a school —
    two rows would be two answers to a question that has one."""
    child = make_person(db)
    school = make_school(db)
    db.commit()

    db.add(
        StudentLoginAuthorization(school_id=school.id, student_person_id=child.id)
    )
    db.commit()

    db.add(
        StudentLoginAuthorization(
            school_id=school.id, student_person_id=child.id, login_enabled=True
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_the_decision_cannot_float_free_of_a_school(db: Session) -> None:
    """`school_id` is NOT NULL: an authorization with no school is exactly the
    global row this change removed."""
    child = make_person(db)
    db.commit()

    db.add(StudentLoginAuthorization(student_person_id=child.id))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_closing_a_school_takes_its_decisions_with_it(db: Session) -> None:
    """`ON DELETE CASCADE`: a school's answer has no meaning once the school is
    gone, and it must not linger as a decision nobody can see or revoke.

    The child and the other school's answer are untouched — that is the whole
    point of the row being per school.
    """
    child = make_person(db)
    closing = make_school(db, name="Zatvara se")
    staying = make_school(db, name="Ostaje")
    db.commit()
    db.add_all([
        StudentLoginAuthorization(
            school_id=closing.id, student_person_id=child.id, login_enabled=True
        ),
        StudentLoginAuthorization(
            school_id=staying.id, student_person_id=child.id, login_enabled=True
        ),
    ])
    db.commit()

    db.execute(
        text("DELETE FROM student_login_authorization WHERE school_id = :s"),
        {"s": closing.id},
    )
    db.commit()

    remaining = db.execute(
        text(
            "SELECT school_id FROM student_login_authorization"
            " WHERE student_person_id = :p"
        ),
        {"p": child.id},
    ).scalars().all()
    assert remaining == [staying.id]
    # The person is global and survives either way.
    assert db.execute(
        text("SELECT count(*) FROM person WHERE id = :p"), {"p": child.id}
    ).scalar_one() == 1


def test_the_person_stays_global(db: Session) -> None:
    """§7.5: the tenant column goes on the authorization, never on `person`.

    A `school_id` on `person` would be the false tenant the contract forbids —
    the same human is the same human in every school they attend.
    """
    columns = {
        row[0]
        for row in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'person'"
            )
        ).all()
    }
    assert "school_id" not in columns


def test_the_global_unique_key_is_gone(db: Session) -> None:
    """Read out of `pg_constraint`, because the behavioural tests above would
    also pass against a table that merely dropped the constraint without
    gaining a tenant — and that would be worse than either shape."""
    uniques = {
        row[0]
        for row in db.execute(
            text(
                "SELECT array_to_string(ARRAY("
                "  SELECT attname FROM unnest(c.conkey) k"
                "  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k"
                "  ORDER BY attname"
                "), ',')"
                " FROM pg_constraint c"
                " WHERE c.contype = 'u'"
                " AND c.conrelid = 'student_login_authorization'::regclass"
            )
        ).all()
    }
    assert "student_person_id" not in uniques, "the global key must be gone"
    assert "school_id,student_person_id" in uniques
