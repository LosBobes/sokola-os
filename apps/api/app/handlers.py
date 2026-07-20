"""Central registration point for outbox event handlers.

Each domain exposes a ``register(...)`` that binds its handlers to event types.
Importing this module wires them all. It is imported by the worker entrypoint
and by tests that exercise delivery.
"""

from __future__ import annotations

from app.domains.communications import outbox as communications_outbox


def register_all() -> None:
    """Register every domain's outbox handlers. Extended per increment."""
    communications_outbox.register()


register_all()
