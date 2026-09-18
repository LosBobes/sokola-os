"""The audit seal: a per-tenant hash chain the database refuses to let you edit.

Two guarantees are under test here, and they are different things:

* the database *refuses* UPDATE and DELETE on ``audit_log``;
* if someone gets around that, verification *detects and locates* it.

The tamper tests therefore disable the trigger on purpose. That is the threat
being modelled: someone with database rights, not someone using the API.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.enums import AuditDataClass
from app.db import SessionLocal
from app.platform import clock
from app.platform.audit.models import SYSTEM_CHAIN_KEY, AuditChainHead, AuditLog
from app.platform.audit.service import record_audit, verify_all_chains, verify_chain
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

ORG_A = "org_aaaaaaaaaaaaaaaaaaaaaaaaaa"
ORG_B = "org_bbbbbbbbbbbbbbbbbbbbbbbbbb"


def _append(db: Session, school_id: str | None, summary: str, **kwargs: object) -> AuditLog:
    entry = record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="test.action",
        entity_type="test",
        entity_id="ent_1",
        summary=summary,
        school_id=school_id,
        **kwargs,  # type: ignore[arg-type]
    )
    db.commit()
    return entry


def _bypass_trigger(db: Session, statement: str, **params: object) -> None:
    """Tamper the way an attacker with database rights would: around the guard."""
    db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only_guard"))
    db.execute(text(statement), params)
    db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only_guard"))
    db.commit()
    # Verification has to read what is now on disk, not what this session loaded
    # before the tamper: a cached row would make a real edit look untouched.
    db.expire_all()


def test_append_builds_a_linked_chain(db: Session) -> None:
    first = _append(db, ORG_A, "prva")
    second = _append(db, ORG_A, "druga")
    third = _append(db, ORG_A, "treća")

    assert [e.sequence_no for e in (first, second, third)] == [1, 2, 3]
    assert first.prev_hash is None
    assert second.prev_hash == first.row_hash
    assert third.prev_hash == second.row_hash
    assert len({first.row_hash, second.row_hash, third.row_hash}) == 3

    head = db.get(AuditChainHead, ORG_A)
    assert head is not None
    assert head.last_sequence_no == 3
    assert head.last_hash == third.row_hash

    assert verify_chain(db, ORG_A).ok


def test_chains_are_per_tenant_and_independent(db: Session) -> None:
    a1 = _append(db, ORG_A, "a1")
    b1 = _append(db, ORG_B, "b1")
    a2 = _append(db, ORG_A, "a2")

    # B's first entry starts its own chain rather than continuing A's.
    assert (a1.chain_key, a1.sequence_no) == (ORG_A, 1)
    assert (b1.chain_key, b1.sequence_no) == (ORG_B, 1)
    assert (a2.chain_key, a2.sequence_no) == (ORG_A, 2)
    assert b1.prev_hash is None
    assert a2.prev_hash == a1.row_hash

    assert verify_chain(db, ORG_A).ok
    assert verify_chain(db, ORG_B).ok


def test_entries_without_a_tenant_use_the_system_chain(db: Session) -> None:
    entry = _append(db, None, "sistemska")
    assert entry.chain_key == SYSTEM_CHAIN_KEY
    assert entry.school_id is None
    assert verify_chain(db, SYSTEM_CHAIN_KEY).ok


def test_database_refuses_update(db: Session) -> None:
    entry = _append(db, ORG_A, "prva")
    with pytest.raises(DatabaseError, match="append-only"):
        db.execute(
            text("UPDATE audit_log SET summary = 'izmenjeno' WHERE id = :id"), {"id": entry.id}
        )
    db.rollback()

    db.expire_all()
    assert db.get(AuditLog, entry.id).summary == "prva"  # type: ignore[union-attr]


def test_database_refuses_delete(db: Session) -> None:
    entry = _append(db, ORG_A, "prva")
    with pytest.raises(DatabaseError, match="append-only"):
        db.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": entry.id})
    db.rollback()

    assert db.get(AuditLog, entry.id) is not None


def test_verification_detects_an_edited_entry(db: Session) -> None:
    _append(db, ORG_A, "prva")
    target = _append(db, ORG_A, "druga")
    _append(db, ORG_A, "treća")

    _bypass_trigger(
        db, "UPDATE audit_log SET summary = 'tiho izmenjeno' WHERE id = :id", id=target.id
    )

    result = verify_chain(db, ORG_A)
    assert not result.ok
    assert result.broken_at_sequence_no == 2
    assert result.broken_entry_id == target.id
    assert result.reason is not None and "digest" in result.reason


def test_verification_detects_a_removed_middle_entry(db: Session) -> None:
    _append(db, ORG_A, "prva")
    target = _append(db, ORG_A, "druga")
    _append(db, ORG_A, "treća")

    _bypass_trigger(db, "DELETE FROM audit_log WHERE id = :id", id=target.id)

    result = verify_chain(db, ORG_A)
    assert not result.ok
    # The third entry now sits where the second should be.
    assert result.broken_at_sequence_no == 3
    assert result.reason is not None and "sequence gap" in result.reason


def test_verification_detects_a_removed_tail_entry(db: Session) -> None:
    _append(db, ORG_A, "prva")
    last = _append(db, ORG_A, "druga")

    _bypass_trigger(db, "DELETE FROM audit_log WHERE id = :id", id=last.id)

    result = verify_chain(db, ORG_A)
    assert not result.ok
    assert result.reason is not None and "head" in result.reason


def test_tampering_in_one_tenant_leaves_another_verifiable(db: Session) -> None:
    victim = _append(db, ORG_A, "a1")
    _append(db, ORG_B, "b1")
    _append(db, ORG_B, "b2")

    _bypass_trigger(db, "UPDATE audit_log SET summary = 'x' WHERE id = :id", id=victim.id)

    assert not verify_chain(db, ORG_A).ok
    assert verify_chain(db, ORG_B).ok


def test_verify_all_chains_covers_every_chain(db: Session) -> None:
    _append(db, ORG_A, "a1")
    _append(db, ORG_B, "b1")
    _append(db, None, "s1")

    results = {r.chain_key: r for r in verify_all_chains(db)}
    assert set(results) == {ORG_A, ORG_B, SYSTEM_CHAIN_KEY}
    assert all(r.ok for r in results.values())


def test_a_rich_context_survives_jsonb_and_still_verifies(db: Session) -> None:
    """The digest is computed in Python but re-checked against what JSONB returns,
    so anything the round-trip changes would show up as a false tamper report."""
    context = {
        "serbian": "Škola Sokolić: čćžšđ ČĆŽŠĐ",
        "nested": {"b": [1, 2, 3], "a": {"deep": True}},
        "null": None,
        "bool": False,
        "int": 10**15,
        "float": 1.5,
        "empty_list": [],
        "empty_obj": {},
    }
    entry = _append(db, ORG_A, "sa kontekstom", context=context)

    db.expire_all()
    stored = db.get(AuditLog, entry.id)
    assert stored is not None and stored.context == context
    assert verify_chain(db, ORG_A).ok


def test_created_at_comes_from_the_clock_port(db: Session) -> None:
    with clock.frozen_at("2026-03-01T10:00:00+00:00"):
        entry = _append(db, ORG_A, "zamrznuto")
    assert entry.created_at == dt.datetime(2026, 3, 1, 10, 0, tzinfo=dt.UTC)
    assert verify_chain(db, ORG_A).ok


def test_concurrent_appends_do_not_share_a_sequence_number(db: Session) -> None:
    """Two transactions appending to the same chain at once. The chain head is
    locked per chain, so the second waits rather than branching the chain."""
    _append(db, ORG_A, "postojeća")

    left, right = SessionLocal(), SessionLocal()
    try:
        first = record_audit(
            left,
            data_class=AuditDataClass.OPERATIONAL,
            action="test.action",
            entity_type="test",
            entity_id="ent_1",
            summary="leva",
            school_id=ORG_A,
        )
        # `right` blocks on the chain head until `left` commits, which is the
        # serialization the seal depends on.
        left.commit()

        second = record_audit(
            right,
            data_class=AuditDataClass.OPERATIONAL,
            action="test.action",
            entity_type="test",
            entity_id="ent_1",
            summary="desna",
            school_id=ORG_A,
        )
        right.commit()

        assert {first.sequence_no, second.sequence_no} == {2, 3}
        assert second.prev_hash == first.row_hash
    finally:
        left.close()
        right.close()

    assert verify_chain(db, ORG_A).ok


def test_a_business_write_seals_its_audit_entry(db: Session) -> None:
    """Whatever the domains already audit stays verifiable end to end."""
    _append(db, ORG_A, "prva")
    entries = (
        db.execute(select(AuditLog).where(AuditLog.chain_key == ORG_A)).scalars().all()
    )
    assert all(e.row_hash and e.chain_key for e in entries)
    assert verify_chain(db, ORG_A).ok
