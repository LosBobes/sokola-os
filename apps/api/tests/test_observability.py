"""PII-free observability: a failure must be describable without quoting a row.

The rule (§3) is that logs, metrics, events and dead-letter records carry no
token, credential, raw contact, child's name, document or message content, bank
reference or amount. The way that rule gets broken is not malice, it is
``repr(exc)``: SQLAlchemy appends the statement and its bound parameters, and
PostgreSQL's DETAIL adds the failing row. These tests drive the real worker
failure path and assert the stored error is clean.
"""

from __future__ import annotations

import pytest
from app.domains.communications.models import Notification
from app.platform import observability
from app.platform.outbox import service, worker
from app.platform.outbox.models import OutboxMessage
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

CHILD_NAME = "Ana Marković"
CONTACT = "ana.markovic@example.invalid"
BANK_REFERENCE = "265104031000012345"


@pytest.fixture(autouse=True)
def _reset_handlers() -> None:
    worker._HANDLERS.clear()


def test_a_database_failure_is_described_by_schema_not_by_data(db: Session) -> None:
    """The real path: a handler fails inserting a row that carries a child's
    name and a guardian's contact. Neither may reach last_error."""

    def insert_bad_notification(session: Session, message: OutboxMessage) -> None:
        session.add(
            Notification(
                school_id="org_missing",  # no such school -> FK violation
                person_id="per_missing",
                event_type="test.pii",
                entity_type="event",
                entity_id="evt_1",
                title="Prijava potvrđena",
                body=f"Dete {CHILD_NAME}, kontakt {CONTACT}, referenca {BANK_REFERENCE}",
                source_message_id=message.id,
            )
        )
        session.flush()

    worker.register_handler("test.pii", insert_bad_notification)
    message = service.enqueue(db, event_type="test.pii", payload={}, school_id="org_x")
    db.commit()

    worker.process_available("w1")

    db.expire_all()
    stored = db.get(OutboxMessage, message.id)
    assert stored is not None
    assert stored.last_error is not None, "the failure still has to be recorded"

    for secret in (CHILD_NAME, CONTACT, BANK_REFERENCE):
        assert secret not in stored.last_error, f"{secret!r} leaked into last_error"
    # Still useful: it names what broke.
    assert "IntegrityError" in stored.last_error or "sqlstate" in stored.last_error


def test_safe_error_keeps_the_diagnosis_for_a_database_error(db: Session) -> None:
    try:
        db.add(
            Notification(
                school_id="org_missing",
                person_id="per_missing",
                event_type="e",
                entity_type="t",
                entity_id="i",
                title="t",
                body=CHILD_NAME,
                source_message_id="obx_missing",
            )
        )
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        described = observability.safe_error(exc)
    else:  # pragma: no cover - the insert must fail for the test to mean anything
        pytest.fail("expected the foreign key to reject this row")

    assert CHILD_NAME not in described
    # 23503 is foreign_key_violation: the school does not exist. The point
    # is that the description names the schema object, never the row.
    assert "sqlstate=23503" in described
    assert "notification" in described


def test_redact_removes_the_blocks_that_quote_row_values() -> None:
    raw = (
        "(psycopg.errors.UniqueViolation) duplicate key value\n"
        f"DETAIL:  Failing row contains (per_1, {CHILD_NAME}, {CONTACT}).\n"
        "[SQL: INSERT INTO person (id, given_name) VALUES (%(id)s, %(given_name)s)]\n"
        f"[parameters: {{'id': 'per_1', 'given_name': '{CHILD_NAME}'}}]"
    )
    cleaned = observability.redact(raw)

    assert CHILD_NAME not in cleaned
    assert CONTACT not in cleaned
    assert "duplicate key value" in cleaned


def test_redact_masks_contacts_and_long_digit_runs() -> None:
    cleaned = observability.redact(
        f"payment for {CONTACT} reference {BANK_REFERENCE} phone 0641234567"
    )
    assert CONTACT not in cleaned
    assert BANK_REFERENCE not in cleaned
    assert "0641234567" not in cleaned
    assert "<email>" in cleaned and "<digits>" in cleaned


def test_redact_truncates_a_runaway_message() -> None:
    cleaned = observability.redact("x" * 5000)
    assert len(cleaned) <= 310


def test_safe_error_falls_back_to_the_type_for_a_plain_exception() -> None:
    described = observability.safe_error(RuntimeError(f"provider rejected {CONTACT}"))
    assert CONTACT not in described
    assert "RuntimeError" in described


def test_a_plain_handler_failure_still_records_something_useful(db: Session) -> None:
    def boom(_db: Session, _message: OutboxMessage) -> None:
        raise RuntimeError("provider down")

    worker.register_handler("test.plain", boom)
    message = service.enqueue(db, event_type="test.plain", payload={}, school_id="org_x")
    db.commit()

    worker.process_available("w1")

    db.expire_all()
    stored = db.get(OutboxMessage, message.id)
    assert stored is not None
    assert stored.last_error is not None
    assert "provider down" in stored.last_error
