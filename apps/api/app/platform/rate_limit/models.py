"""The counter behind M01 §10's limits.

A fixed-window counter in Postgres, because that is what this deployment has —
there is no Redis, and a limit that exists is worth more than a smoother one
that does not. The window boundary is the honest weakness: an attacker who
times a burst across two adjacent windows gets up to twice the budget in a
short span. That is acceptable here because these limits exist to blunt
automated volume, not to be the only thing standing between an attacker and an
account — the credential checks are.

What is stored is a **keyed digest** of the address or device signal, never the
signal itself (§10: "Limiti su keyed hash IP/device signal-a i kratko se čuvaju
prema M17; ne koriste se za profilisanje"). The row cannot be turned back into
an IP, and `expires_at` is there so it does not have to be kept.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base
from app.common.columns import enum_type
from app.common.ids import new_id
from app.platform.rate_limit.enums import RateLimitScope


class RateLimitCounter(Base):
    """One (scope, subject digest, window) bucket."""

    __tablename__ = "rate_limit_counter"
    __table_args__ = (
        UniqueConstraint(
            "scope", "subject_hash", "window_start", name="uq_rate_limit_bucket"
        ),
        CheckConstraint("hits > 0", name="ck_rate_limit_hits"),
        # The sweep's index. Without it, retention becomes a table scan on the
        # one table that grows fastest under attack — exactly when it must not.
        Index("ix_rate_limit_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rlc"))
    scope: Mapped[RateLimitScope] = mapped_column(enum_type(RateLimitScope), nullable=False)
    #: Keyed HMAC-SHA-256 of the signal. Keyed rather than plain, so a stolen
    #: table cannot be brute-forced back to a list of addresses — the IPv4
    #: space is small enough to enumerate against an unkeyed digest in minutes.
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hits: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    #: M17 retention. These rows answer "how many in the last ten minutes" and
    #: nothing else, so they have no reason to outlive the window.
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
