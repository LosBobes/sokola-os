"""Idempotency guard for financial / registration / import / notification writes.

Usage from a domain service::

    guard = idempotency.begin(session, org_id, "payments.record", key, params)
    if guard.replay is not None:
        return guard.replay            # same key + same params -> stored result
    ... do the work ...
    idempotency.complete(session, guard, status=201, body=result)

A different parameter set under the same key raises ``IdempotencyConflictError``.
A concurrent in-flight request under the same key raises ``ConflictError``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, IdempotencyConflictError
from app.platform.idempotency.enums import IdempotencyStatus
from app.platform.idempotency.models import IdempotencyRecord


def hash_params(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class Guard:
    record: IdempotencyRecord
    # {"status": int, "body": <object or array>} when replaying, else None.
    replay: dict[str, Any] | None


def begin(
    session: Session,
    organization_id: str,
    operation: str,
    idempotency_key: str,
    params: dict[str, Any],
) -> Guard:
    request_hash = hash_params(params)
    existing = session.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == organization_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyConflictError(
                "Isti ključ je već korišćen sa drugačijim podacima."
            )
        if existing.status is IdempotencyStatus.COMPLETED:
            return Guard(
                record=existing,
                replay={"status": existing.response_status, "body": existing.response_body},
            )
        # Still in progress elsewhere: the client must retry after it settles.
        raise ConflictError("Operacija sa ovim ključem je već u toku.")

    record = IdempotencyRecord(
        organization_id=organization_id,
        operation=operation,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status=IdempotencyStatus.IN_PROGRESS,
    )
    session.add(record)
    try:
        session.flush()  # unique constraint resolves the concurrent-insert race
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("Operacija sa ovim ključem je već u toku.") from exc
    return Guard(record=record, replay=None)


def complete(session: Session, guard: Guard, *, status: int, body: Any) -> None:
    guard.record.status = IdempotencyStatus.COMPLETED
    guard.record.response_status = status
    guard.record.response_body = body
    session.flush()
