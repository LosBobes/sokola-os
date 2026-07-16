"""Outbox worker loop and handler registry.

Handlers are registered per event type. Delivery is at-least-once, so every
handler must be idempotent. Unknown event types are treated as delivered (there
is nothing to do) but logged for visibility.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from app.db import SessionLocal
from app.platform.outbox import service
from app.platform.outbox.models import OutboxMessage

logger = logging.getLogger("sokola.outbox")

Handler = Callable[[OutboxMessage], None]
_HANDLERS: dict[str, Handler] = {}


def register_handler(event_type: str, handler: Handler) -> None:
    _HANDLERS[event_type] = handler


def _dispatch(message: OutboxMessage) -> None:
    handler = _HANDLERS.get(message.event_type)
    if handler is None:
        logger.info("no handler for event_type=%s; skipping", message.event_type)
        return
    handler(message)


def process_available(worker_id: str, *, batch_size: int = 20) -> int:
    """Claim and process one batch. Returns the number handled. Each message is
    committed independently so one poison message can't block the batch."""
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
                _dispatch(message)
                service.mark_delivered(session, message)
            except Exception as exc:  # noqa: BLE001 - transient handler failures are expected
                service.mark_failed(session, message, repr(exc))
                logger.warning("outbox delivery failed id=%s: %r", message.id, exc)
            session.commit()
            processed += 1
    return processed


def run_forever(worker_id: str, *, poll_seconds: float = 1.0) -> None:  # pragma: no cover
    logger.info("outbox worker %s starting", worker_id)
    while True:
        handled = process_available(worker_id)
        if handled == 0:
            time.sleep(poll_seconds)


def registered_event_types() -> list[str]:
    return sorted(_HANDLERS)


def _noop(_: Any) -> None:  # pragma: no cover
    return None
