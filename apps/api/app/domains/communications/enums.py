from __future__ import annotations

import enum


class AnnouncementStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class AnnouncementTargetType(enum.StrEnum):
    ORGANIZATION = "ORGANIZATION"
    GROUP = "GROUP"


class NotificationDeliveryStatus(enum.StrEnum):
    """Delivery state of a single in-app :class:`Notification` row.

    v1 has exactly one channel — the in-app inbox — so ``DELIVERED`` simply
    means the row was committed successfully; there is no external send step
    yet (email/push are out of scope, see PRD 08 M4). The states still model a
    real state machine so a future channel can slot in without a schema change:

    * ``PENDING`` — the row is being constructed; never observed once committed
      (a handler either finishes and commits as ``DELIVERED``, or the whole
      outbox message fails and retries — see ``app.platform.outbox``).
    * ``DELIVERED`` — the in-app record exists and is visible in the recipient's
      inbox. Terminal for v1.
    * ``FAILED`` — reserved for a future external channel's delivery failure;
      unused today because in-app "delivery" cannot partially fail (either the
      transaction commits, or the outbox retries the whole event).
    """

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
