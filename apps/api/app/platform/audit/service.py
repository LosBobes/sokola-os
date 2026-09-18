"""Audit port: an append-only, tamper-evident trail.

Every entry is appended inside the caller's transaction, so a business write and
its audit entry commit or roll back together. Each entry is sealed into a
per-tenant hash chain:

    row_hash = SHA-256( canonical(entry fields) + prev_hash )

Editing an entry, deleting one, or splicing one in changes that entry's digest
and therefore breaks every digest after it. :func:`verify_chain` walks a chain
and reports the first position where it stops adding up. The database also
refuses ``UPDATE`` and ``DELETE`` outright, so tampering means going around the
application, and even then it cannot be made to look consistent.

Chains are keyed per school (plus one reserved chain for entries with no
tenant), so appending serializes only against other writes in the same school.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.platform import clock
from app.platform.audit.models import SYSTEM_CHAIN_KEY, AuditChainHead, AuditLog


def chain_key_for(school_id: str | None) -> str:
    return school_id or SYSTEM_CHAIN_KEY


def compute_digest(
    *,
    chain_key: str,
    sequence_no: int,
    prev_hash: str | None,
    school_id: str | None,
    actor_person_id: str | None,
    data_class: AuditDataClass | str,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    context: dict[str, Any] | None,
    created_at: dt.datetime,
) -> str:
    """The digest of one entry, over its content and its predecessor's digest.

    The encoding is canonical (sorted keys, no insignificant whitespace, UTC
    instants) so that recomputing it from what the database returns yields the
    same string it did at write time. ``context`` has to be JSON-serializable,
    which it already must be to reach a JSONB column at all.
    """
    payload = {
        "chain_key": chain_key,
        "sequence_no": sequence_no,
        "prev_hash": prev_hash,
        "school_id": school_id,
        "actor_person_id": actor_person_id,
        "data_class": data_class.value if isinstance(data_class, AuditDataClass) else data_class,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "summary": summary,
        "context": context,
        "created_at": created_at.astimezone(dt.UTC).isoformat(),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _claim_chain_head(session: Session, chain_key: str) -> tuple[int, str | None]:
    """Lock this chain's head (creating it on first use) and return its tip.

    ``ON CONFLICT DO UPDATE`` with a no-op assignment is the atomic
    lock-or-insert: a plain ``SELECT ... FOR UPDATE`` cannot lock a row that does
    not exist yet, which is exactly the race two concurrent first-writes hit.
    """
    row = session.execute(
        text(
            "INSERT INTO audit_chain_head (chain_key, last_sequence_no, last_hash,"
            "                              created_at, updated_at) "
            "VALUES (:k, 0, NULL, now(), now()) "
            "ON CONFLICT (chain_key) DO UPDATE SET chain_key = EXCLUDED.chain_key "
            "RETURNING last_sequence_no, last_hash"
        ),
        {"k": chain_key},
    ).one()
    return int(row[0]), row[1]


def record_audit(
    session: Session,
    *,
    data_class: AuditDataClass,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    school_id: str | None = None,
    actor_person_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> AuditLog:
    """Append a sealed audit entry within the caller's transaction."""
    chain_key = chain_key_for(school_id)
    last_sequence_no, last_hash = _claim_chain_head(session, chain_key)

    sequence_no = last_sequence_no + 1
    created_at = clock.now()
    row_hash = compute_digest(
        chain_key=chain_key,
        sequence_no=sequence_no,
        prev_hash=last_hash,
        school_id=school_id,
        actor_person_id=actor_person_id,
        data_class=data_class,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        context=context,
        created_at=created_at,
    )

    entry = AuditLog(
        school_id=school_id,
        actor_person_id=actor_person_id,
        data_class=data_class,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        context=context,
        chain_key=chain_key,
        sequence_no=sequence_no,
        prev_hash=last_hash,
        row_hash=row_hash,
        created_at=created_at,
    )
    session.add(entry)
    session.flush()

    session.execute(
        update(AuditChainHead)
        .where(AuditChainHead.chain_key == chain_key)
        .values(last_sequence_no=sequence_no, last_hash=row_hash)
    )
    return entry


@dataclass(frozen=True, slots=True)
class ChainVerification:
    """What a verification pass found.

    ``ok`` is the only thing a caller needs to branch on; the rest says where to
    look. ``broken_at_sequence_no`` is the first entry that does not add up, and
    ``reason`` says how.
    """

    chain_key: str
    ok: bool
    entries_checked: int
    broken_at_sequence_no: int | None = None
    broken_entry_id: str | None = None
    reason: str | None = None


def verify_chain(session: Session, chain_key: str) -> ChainVerification:
    """Recompute a whole chain and report the first break.

    Catches an edited entry (its digest no longer matches its content), a removed
    or missing one (a gap in the sequence, or a predecessor digest that points at
    nothing), and a chain whose stored head disagrees with its last entry.
    """
    entries = (
        session.execute(
            select(AuditLog)
            .where(AuditLog.chain_key == chain_key)
            .order_by(AuditLog.sequence_no)
        )
        .scalars()
        .all()
    )

    def broken(entry: AuditLog, reason: str) -> ChainVerification:
        return ChainVerification(
            chain_key=chain_key,
            ok=False,
            entries_checked=len(entries),
            broken_at_sequence_no=entry.sequence_no,
            broken_entry_id=entry.id,
            reason=reason,
        )

    expected_prev: str | None = None
    expected_sequence_no = 1
    for entry in entries:
        if entry.sequence_no != expected_sequence_no:
            return broken(
                entry,
                f"sequence gap: expected {expected_sequence_no}, found {entry.sequence_no}",
            )
        if entry.prev_hash != expected_prev:
            return broken(entry, "previous digest does not match the preceding entry")

        recomputed = compute_digest(
            chain_key=entry.chain_key,
            sequence_no=entry.sequence_no,
            prev_hash=entry.prev_hash,
            school_id=entry.school_id,
            actor_person_id=entry.actor_person_id,
            data_class=entry.data_class,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            summary=entry.summary,
            context=entry.context,
            created_at=entry.created_at,
        )
        if recomputed != entry.row_hash:
            return broken(entry, "entry content does not match its digest")

        expected_prev = entry.row_hash
        expected_sequence_no += 1

    head = session.get(AuditChainHead, chain_key)
    if head is not None and (
        head.last_sequence_no != len(entries) or head.last_hash != expected_prev
    ):
        return ChainVerification(
            chain_key=chain_key,
            ok=False,
            entries_checked=len(entries),
            broken_at_sequence_no=head.last_sequence_no,
            reason="chain head does not match the last entry (entries removed from the tail?)",
        )

    return ChainVerification(chain_key=chain_key, ok=True, entries_checked=len(entries))


def verify_all_chains(session: Session) -> list[ChainVerification]:
    """Verify every known chain. The M21 audit-verification job's entry point."""
    keys = session.execute(select(AuditChainHead.chain_key).order_by(AuditChainHead.chain_key))
    return [verify_chain(session, key) for key in keys.scalars().all()]
