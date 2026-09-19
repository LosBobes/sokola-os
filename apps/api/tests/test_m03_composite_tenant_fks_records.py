"""M03 §7.2–7.3, third slice: what a school accumulates.

The first two slices covered the structure a school is arranged into and the
day it runs. These are the records it keeps — announcements, registrations,
money, imports, the locator's own history, and who has owned the school.

Seven of the eight follow the pattern exactly. The eighth, the outbox's
dead-letter review, is handled differently on purpose; there is a test below
that says why and proves the difference is real.

As in the earlier slices, every test writes the row itself rather than going
through the service layer, because the service layer is where the old check
lived. What is being proved is that the database refuses.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from app.common.ids import new_id
from app.domains.billing.models import BillingRun, Charge
from app.domains.communications.enums import AnnouncementTargetType
from app.domains.communications.models import Announcement, AnnouncementRecipient
from app.domains.data_import.models import ImportBatch, ImportRow
from app.domains.events.models import Event, EventRegistration
from app.domains.identity.models import Person
from app.domains.payments.enums import PaymentMethod
from app.domains.payments.models import PaymentRecord
from app.domains.school.enums import LocatorKind, LocatorStatus
from app.domains.school.models import School, SchoolLocator
from app.domains.school.ownership_enums import OwnerNominationKind
from app.domains.school.ownership_models import SchoolOwnerNomination
from app.platform import clock
from app.platform.outbox.enums import DeadLetterAction
from app.platform.outbox.models import DeadLetterReview, OutboxMessage
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school

#: (child table, child column, the parent kind it must stay inside)
RELATIONS = [
    ("announcement_recipient", "announcement_id", "announcement"),
    ("event_registration", "event_id", "event"),
    ("charge", "billing_run_id", "billing_run"),
    ("payment_record", "charge_id", "charge"),
    ("import_row", "batch_id", "import_batch"),
    ("school_locator", "replaced_by_locator_id", "locator"),
    ("school_primary_owner_term", "source_nomination_id", "nomination"),
    ("outbox_dead_letter_review", "message_id", "message"),
]


def _records(db: Session, school: School, person: Person) -> dict[str, str]:
    """One of each parent record, all belonging to `school`."""
    now = clock.now()
    school_id, person_id = school.id, person.id
    # The nomination names a profile through a composite key of its own
    # (school + profile + person), so the profile has to exist first.
    profile = ensure_person_profile(db, school=school, person=person)
    announcement = Announcement(
        school_id=school_id,
        title="Obaveštenje",
        body="Tekst",
        target_type=AnnouncementTargetType.SCHOOL,
        snapshot_hash="h",
    )
    event = Event(school_id=school_id, title="Dogadjaj", starts_at=now)
    billing_run = BillingRun(
        school_id=school_id, description="Mart", period_label="2026-03", currency="RSD"
    )
    batch = ImportBatch(
        school_id=school_id, source_filename="ljudi.csv", created_by_person_id=person_id
    )
    nomination = SchoolOwnerNomination(
        school_id=school_id,
        target_person_id=person_id,
        target_school_person_profile_id=profile.id,
        # ADDITIONAL_OWNER rather than INITIAL: a partial unique index allows
        # only one pending initial-primary-owner nomination per school, and
        # this fixture has no business competing for that slot.
        kind=OwnerNominationKind.ADDITIONAL_OWNER,
        created_by_actor_ref="test",
    )
    message = OutboxMessage(school_id=school_id, event_type="test.event", payload={})
    db.add_all([announcement, event, billing_run, batch, nomination, message])
    db.flush()
    # The school already has exactly one ACTIVE locator — `make_school` creates
    # it, and a partial unique index allows only one per kind. So the
    # replacement a retired locator points at is that one, which is also what
    # a real rotation looks like.
    locator_id = db.execute(
        text(
            "SELECT id FROM school_locator"
            " WHERE school_id = :id AND status = 'ACTIVE' AND kind = 'SLUG'"
        ),
        {"id": school_id},
    ).scalar_one()
    charge = Charge(
        school_id=school_id,
        person_id=person_id,
        description="Članarina",
        currency="RSD",
        amount_due=Decimal("1000.00"),
    )
    db.add(charge)
    db.flush()
    return {
        "announcement": announcement.id,
        "event": event.id,
        "billing_run": billing_run.id,
        "charge": charge.id,
        "import_batch": batch.id,
        "locator": locator_id,
        "nomination": nomination.id,
        "message": message.id,
    }


def _retired_locator(school_id: str, *, replaced_by: str | None) -> SchoolLocator:
    """A retired locator for `school_id`, optionally naming its replacement.

    Retired rather than active because a school may hold only one active
    locator per kind (a partial unique index), and because only a retired
    locator has a replacement at all — an active one is the replacement.
    """
    now = clock.now()
    return SchoolLocator(
        school_id=school_id,
        kind=LocatorKind.SLUG,
        normalized_value=new_id("slug"),
        valid_from=now,
        retired_at=now + dt.timedelta(seconds=1),
        status=LocatorStatus.RETIRED,
        created_by_actor_ref="test",
        replaced_by_locator_id=replaced_by,
    )


def _child(
    table: str, *, school_id: str, target_id: str | None, person_id: str
) -> object:
    """A child row for `table`, with the reference under test set to
    `target_id`. Built from the mapped class: the point is to skip the service
    layer, not the ORM."""
    now = clock.now()
    if table == "announcement_recipient":
        return AnnouncementRecipient(
            school_id=school_id, announcement_id=target_id, person_id=person_id
        )
    if table == "event_registration":
        return EventRegistration(
            school_id=school_id,
            event_id=target_id,
            child_person_id=person_id,
            registered_by_person_id=person_id,
        )
    if table == "charge":
        return Charge(
            school_id=school_id,
            person_id=person_id,
            billing_run_id=target_id,
            description="Iz obrade",
            currency="RSD",
            amount_due=Decimal("500.00"),
        )
    if table == "payment_record":
        return PaymentRecord(
            school_id=school_id,
            charge_id=target_id,
            amount=Decimal("100.00"),
            currency="RSD",
            method=PaymentMethod.CASH,
        )
    if table == "import_row":
        return ImportRow(
            school_id=school_id,
            batch_id=target_id,
            row_number=1,
            given_name="Ana",
            family_name="Marković",
        )
    if table == "school_locator":
        return _retired_locator(school_id, replaced_by=target_id)
    if table == "school_primary_owner_term":
        # Not built here: this one needs a real OWNER role assignment to satisfy
        # the four-column key it already had. See its own test below.
        raise AssertionError("built by its own test")
    if table == "outbox_dead_letter_review":
        return DeadLetterReview(
            school_id=school_id,
            message_id=target_id,
            action=DeadLetterAction.REPLAY,
            requested_by_person_id=person_id,
            requested_at=now,
            request_reason="Proba",
        )
    raise AssertionError(f"no child builder for {table}")


BUILDABLE = [r for r in RELATIONS if r[0] != "school_primary_owner_term"]


@pytest.mark.parametrize("table, column, parent", BUILDABLE)
def test_a_reference_cannot_cross_a_tenant(
    db: Session, table: str, column: str, parent: str
) -> None:
    """School A's record may not name school B's, and the refusal comes from
    the database rather than from anyone remembering."""
    mine = make_school(db, name="Moja")
    theirs = make_school(db, name="Tudja")
    person = make_person(db)
    db.commit()
    _records(db, mine, person)
    other = _records(db, theirs, person)
    db.commit()

    db.add(
        _child(table, school_id=mine.id, target_id=other[parent], person_id=person.id)
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


@pytest.mark.parametrize("table, column, parent", BUILDABLE)
def test_the_same_tenant_still_works(
    db: Session, table: str, column: str, parent: str
) -> None:
    """The constraint must refuse the wrong thing without refusing the right
    one."""
    school = make_school(db, name="Jedna")
    person = make_person(db)
    db.commit()
    own = _records(db, school, person)
    db.commit()

    db.add(
        _child(table, school_id=school.id, target_id=own[parent], person_id=person.id)
    )
    db.commit()


@pytest.mark.parametrize("table, column, parent", RELATIONS)
def test_the_composite_foreign_key_actually_exists(
    db: Session, table: str, column: str, parent: str
) -> None:
    """Names the constraint in the database, not in the model file.

    A behavioural test alone cannot tell a composite key from the single-column
    one it replaced — both refuse an unknown id. This is what tells them apart,
    and it is the only check that covers `school_primary_owner_term`, whose
    rows are too entangled to build here.
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


def test_the_outbox_keeps_its_single_column_key_as_well(db: Session) -> None:
    """The one relation that was added to rather than replaced, and why.

    `school_id` is nullable on both `outbox_message` and its dead-letter
    review, because the outbox also carries platform-level messages belonging
    to no school. Postgres's MATCH SIMPLE skips a composite foreign key
    entirely when any of its columns is NULL — so a composite key *alone* would
    stop checking exactly those rows, which is weaker than what was there
    before, not stronger.

    Both keys therefore exist: this test fails if someone later "tidies up" the
    single-column one for consistency with the other twenty-two.
    """
    keys = {
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
                " AND c.conrelid = 'outbox_dead_letter_review'::regclass"
            )
        ).all()
    }
    assert "message_id" in keys, "the single-column key must survive"
    assert "message_id,school_id" in keys, "the composite key must exist too"


def test_a_platform_message_can_still_be_reviewed(db: Session) -> None:
    """The rows the composite key deliberately does not check.

    A message with no school is a platform message, and its review has no
    school either. Neither is a tenant's, so there is no tenant to agree on —
    and the single-column key is what still guarantees the message exists.
    """
    person = make_person(db)
    message = OutboxMessage(school_id=None, event_type="platform.event", payload={})
    db.add(message)
    db.flush()
    db.add(
        DeadLetterReview(
            school_id=None,
            message_id=message.id,
            action=DeadLetterAction.DISCARD,
            requested_by_person_id=person.id,
            requested_at=clock.now(),
            request_reason="Platformska poruka",
        )
    )
    db.commit()


def test_a_review_still_cannot_invent_a_message(db: Session) -> None:
    """And the single-column key still does its original job: a review of a
    message that does not exist is refused, school or no school."""
    person = make_person(db)
    db.commit()
    db.add(
        DeadLetterReview(
            school_id=None,
            message_id=new_id("obx"),
            action=DeadLetterAction.REPLAY,
            requested_by_person_id=person.id,
            requested_at=clock.now(),
            request_reason="Nepostojeća",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_locator_cannot_be_replaced_by_another_schools_locator(
    db: Session,
) -> None:
    """`replaced_by_locator_id` carried the comment "Same school" and nothing
    else. This is that comment made enforceable: a retired URL can only say it
    was replaced by its own school's, never by someone else's, which would turn
    the rotation history into a pointer at another tenant."""
    mine = make_school(db, name="Moja")
    theirs = make_school(db, name="Tudja")
    db.commit()

    theirs_locator = db.execute(
        text(
            "SELECT id FROM school_locator"
            " WHERE school_id = :id AND status = 'ACTIVE' AND kind = 'SLUG'"
        ),
        {"id": theirs.id},
    ).scalar_one()

    db.add(_retired_locator(mine.id, replaced_by=theirs_locator))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_deleting_a_billing_run_keeps_its_charges(db: Session) -> None:
    """`SET NULL (billing_run_id)` names the column, because the plain form
    would try to null `school_id` and that column is NOT NULL.

    A charge is a debt someone owes. Deleting the run that produced it must
    detach it, never erase it.
    """
    school = make_school(db)
    person = make_person(db)
    db.commit()
    own = _records(db, school, person)
    charge = Charge(
        school_id=school.id,
        person_id=person.id,
        billing_run_id=own["billing_run"],
        description="Članarina",
        currency="RSD",
        amount_due=Decimal("1000.00"),
    )
    db.add(charge)
    db.commit()
    charge_id = charge.id

    db.execute(
        text("DELETE FROM billing_run WHERE id = :id"), {"id": own["billing_run"]}
    )
    db.commit()

    row = db.execute(
        text("SELECT school_id, billing_run_id FROM charge WHERE id = :id"),
        {"id": charge_id},
    ).one()
    assert row.school_id == school.id
    assert row.billing_run_id is None


def test_deleting_a_charge_takes_its_payments(db: Session) -> None:
    """CASCADE is kept here: a payment against a charge that no longer exists
    is not a ledger entry, it is an orphan."""
    school = make_school(db)
    person = make_person(db)
    db.commit()
    own = _records(db, school, person)
    db.add(
        PaymentRecord(
            school_id=school.id,
            charge_id=own["charge"],
            amount=Decimal("100.00"),
            currency="RSD",
            method=PaymentMethod.CASH,
        )
    )
    db.commit()

    db.execute(text("DELETE FROM charge WHERE id = :id"), {"id": own["charge"]})
    db.commit()

    left = db.execute(
        text("SELECT count(*) FROM payment_record WHERE charge_id = :id"),
        {"id": own["charge"]},
    ).scalar_one()
    assert left == 0


@pytest.mark.parametrize(
    "table",
    [
        "announcement",
        "event",
        "billing_run",
        "charge",
        "import_batch",
        "school_locator",
        "school_owner_nomination",
        "outbox_message",
    ],
)
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


def test_no_tenant_reference_is_left_on_a_bare_id(db: Session) -> None:
    """F-26 closed. Every foreign key from one school-scoped table to another
    now carries `school_id`, with exactly one documented exception.

    This is the test that keeps the next such reference from being added
    quietly: a new single-column foreign key between two tenant tables will
    fail here, naming itself.
    """
    stragglers = [
        row[0]
        for row in db.execute(
            text(
                "WITH tenant AS ("
                "  SELECT c.oid, c.relname FROM pg_class c"
                "  JOIN pg_attribute a ON a.attrelid = c.oid"
                "   AND a.attname = 'school_id' AND NOT a.attisdropped"
                "  WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace"
                ")"
                " SELECT ct.relname || '.' || a.attname || ' -> ' || pt.relname"
                " FROM pg_constraint con"
                " JOIN tenant ct ON ct.oid = con.conrelid"
                " JOIN tenant pt ON pt.oid = con.confrelid"
                " JOIN pg_attribute a ON a.attrelid = con.conrelid"
                "  AND a.attnum = con.conkey[1]"
                " WHERE con.contype = 'f'"
                "  AND array_length(con.conkey, 1) = 1"
                "  AND a.attname <> 'school_id'"
                " ORDER BY 1"
            )
        ).all()
    ]
    # The outbox review's single-column key is kept deliberately, next to its
    # composite one — see `test_the_outbox_keeps_its_single_column_key_as_well`.
    assert stragglers == ["outbox_dead_letter_review.message_id -> outbox_message"]
