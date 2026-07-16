from __future__ import annotations

import enum


class OutboxStatus(enum.StrEnum):
    PENDING = "PENDING"  # awaiting delivery (respect available_at)
    PROCESSING = "PROCESSING"  # claimed by a worker (respect lease)
    DELIVERED = "DELIVERED"  # handled successfully
    FAILED = "FAILED"  # transient failure, will retry
    DEAD_LETTER = "DEAD_LETTER"  # exhausted attempts, needs operator attention
