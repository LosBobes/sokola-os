"""Outbox worker loop and handler registry.

Handlers are registered per event type and receive the worker's session. That is
deliberate: the handler's writes, its inbox claim and the message's DELIVERED
status all commit as one transaction, so a message is either fully handled or
not handled at all.

Delivery is still at-least-once (a process can die between the side effect and
the commit), but the inbox claim makes the replay a no-op instead of a
duplicate, so a handler no longer has to invent its own de-duplication. Unknown
event types are treated as delivered (there is nothing to do) but logged.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.platform import observability
from app.platform.inbox import service as inbox
from app.platform.outbox import service
from app.platform.outbox.models import OutboxMessage

logger = logging.getLogger("sokola.outbox")

Handler = Callable[[Session, OutboxMessage], None]


@dataclass(frozen=True, slots=True)
class Registration:
    consumer: str
    handler: Handler


_HANDLERS: dict[str, Registration] = {}


def register_handler(event_type: str, handler: Handler, *, consumer: str | None = None) -> None:
    """Bind ``handler`` to ``event_type``.

    ``consumer`` names who is doing the handling and is what the inbox claim is
    keyed on. It defaults to the event type, which is correct while one handler
    serves one event type; name it explicitly when that stops being true, so the
    claims of two consumers never collide.
    """
    _HANDLERS[event_type] = Registration(consumer=consumer or event_type, handler=handler)


def _dispatch(session: Session, message: OutboxMessage) -> None:
    registration = _HANDLERS.get(message.event_type)
    if registration is None:
        logger.info("no handler for event_type=%s; skipping", message.event_type)
        return
    if not inbox.claim(session, consumer=registration.consumer, message=message):
        logger.info(
            "message id=%s already handled by consumer=%s; skipping",
            message.id,
            registration.consumer,
        )
        return
    registration.handler(session, message)


def process_available(worker_id: str, *, batch_size: int = 20) -> int:
    """Claim and process one batch. Returns the number handled.

    Each message gets its own transaction, so one poison message cannot block
    the batch, and a failure rolls back that handler's partial work before the
    failure is recorded, rather than committing half an effect alongside it.
    """
    processed = 0
    with SessionLocal() as session:
        batch = service.claim_batch(session, worker_id=worker_id, limit=batch_size)
        session.commit()  # persist the claim before doing side effects

    for message_id in [m.id for m in batch]:
        with SessionLocal() as session:
            message = session.get(OutboxMessage, message_id, with_for_update=True)
            if message is None:
                continue
            try:
                _dispatch(session, message)
                service.mark_delivered(session, message)
                session.commit()
            except Exception as exc:  # noqa: BLE001 - transient handler failures are expected
                # Discard whatever the handler managed to write, including its
                # inbox claim, so the retry starts from a clean slate.
                session.rollback()
                # Never the raw exception: it quotes row values, and this line
                # and the stored error are both covered by the PII-free rule.
                description = observability.safe_error(exc)
                _record_failure(message_id, description)
                logger.warning("outbox delivery failed id=%s: %s", message_id, description)
            processed += 1
    return processed


def _record_failure(message_id: str, description: str) -> None:
    """Record the failure in its own transaction, after the rollback above."""
    with SessionLocal() as session:
        message = session.get(OutboxMessage, message_id, with_for_update=True)
        if message is None:
            return
        service.mark_failed(session, message, description)
        session.commit()


def run_forever(worker_id: str, *, poll_seconds: float = 1.0) -> None:  # pragma: no cover
    logger.info("outbox worker %s starting", worker_id)
    while True:
        handled = process_available(worker_id)
        if handled == 0:
            time.sleep(poll_seconds)


def registered_event_types() -> list[str]:
    return sorted(_HANDLERS)
