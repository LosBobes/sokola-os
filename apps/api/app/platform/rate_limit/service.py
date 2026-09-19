"""Counting and refusing, for M01 §6 AUTH-01 and §10.

Two rules shape this module.

**The signal is never stored.** §10 says the limits are keyed hashes of the
IP/device signal, kept briefly per M17, and not used for profiling. So the
address is hashed on the way in and the row cannot be turned back into it. The
key is derived from the session secret by domain separation rather than being
its own deployment variable: a new required secret is a new way for a deploy to
fail, and the security property here — "an attacker who steals this table
cannot enumerate our users' addresses" — is fully served by a key that already
exists and is already required in production.

**A limit that cannot be checked must not silently allow.** Every path that
consumes budget also commits it, in its own short transaction, so a request
that dies later still counted. The alternative — counting in the request's main
transaction — means a failed login rolls back its own failure count, which is
precisely the case the limit exists for.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import RateLimitedError
from app.platform import clock
from app.platform.rate_limit.enums import RateLimitScope
from app.platform.rate_limit.models import RateLimitCounter

#: Domain separator for the derived key. Versioned, so a future change of
#: derivation does not silently reuse old digests under a new meaning.
_KEY_INFO = b"sokola/rate-limit/v1"


@dataclass(frozen=True, slots=True)
class Budget:
    """One scope's allowance: ``limit`` events per ``window``."""

    scope: RateLimitScope
    limit: int
    window: dt.timedelta


#: §6 AUTH-01 and §10, as written. These are security configuration, not
#: defaults anyone should tune casually — the numbers come from the contract.
BUDGETS: dict[RateLimitScope, Budget] = {
    RateLimitScope.LOGIN_START_IP: Budget(
        RateLimitScope.LOGIN_START_IP, limit=5, window=dt.timedelta(minutes=10)
    ),
    RateLimitScope.LOGIN_START_DEVICE: Budget(
        RateLimitScope.LOGIN_START_DEVICE, limit=10, window=dt.timedelta(hours=24)
    ),
    RateLimitScope.CALLBACK_FAILURE_IP: Budget(
        RateLimitScope.CALLBACK_FAILURE_IP, limit=20, window=dt.timedelta(minutes=10)
    ),
    RateLimitScope.PASSWORD_FAILURE_IP: Budget(
        RateLimitScope.PASSWORD_FAILURE_IP, limit=20, window=dt.timedelta(minutes=10)
    ),
}


def subject_hash(signal: str, *, secret: str) -> str:
    """Keyed digest of an address or device id.

    Keyed rather than plain SHA-256 because the input space is tiny: the whole
    IPv4 range fits in a few minutes of unkeyed hashing, so a plain digest of an
    address is the address.
    """
    key = hmac.new(secret.encode("utf-8"), _KEY_INFO, hashlib.sha256).digest()
    return hmac.new(key, signal.encode("utf-8"), hashlib.sha256).hexdigest()


def window_start(now: dt.datetime, window: dt.timedelta) -> dt.datetime:
    """The start of the fixed window ``now`` falls in.

    Anchored to the epoch rather than to first use, so every node computes the
    same boundary without coordinating — two API processes must not each grant
    a full budget because they started at different times.
    """
    seconds = int(window.total_seconds())
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
    elapsed = int((now - epoch).total_seconds())
    return epoch + dt.timedelta(seconds=(elapsed // seconds) * seconds)


def consume(
    db: Session,
    scope: RateLimitScope,
    signal: str,
    *,
    secret: str,
    now: dt.datetime | None = None,
) -> None:
    """Count one event against ``scope`` and raise if it went over.

    Counts *before* deciding, so the event that crosses the line is itself
    counted — an implementation that checked first and counted after would let
    every concurrent request through the same gap.

    Raises :class:`RateLimitedError`, which §11 requires to be generic: it does
    not confirm that an address, a person or an account exists (M01-QA-013).
    """
    budget = BUDGETS[scope]
    moment = now or clock.now()
    start = window_start(moment, budget.window)
    digest = subject_hash(signal, secret=secret)

    hits = _increment(db, scope, digest, start, expires_at=start + budget.window * 2)
    if hits > budget.limit:
        raise RateLimitedError("Previše pokušaja. Pokušajte ponovo kasnije.")


def _increment(
    db: Session,
    scope: RateLimitScope,
    digest: str,
    start: dt.datetime,
    *,
    expires_at: dt.datetime,
) -> int:
    """Add one to the bucket, creating it if this is the first event.

    ``UPDATE ... RETURNING`` rather than read-modify-write: two concurrent
    requests must not both read 4 and both write 5, because that is how a limit
    of 5 admits an unbounded burst.
    """
    updated = db.execute(
        update(RateLimitCounter)
        .where(
            RateLimitCounter.scope == scope,
            RateLimitCounter.subject_hash == digest,
            RateLimitCounter.window_start == start,
        )
        .values(hits=RateLimitCounter.hits + 1)
        .returning(RateLimitCounter.hits)
    ).scalar_one_or_none()
    if updated is not None:
        return int(updated)

    try:
        # A SAVEPOINT, not the whole transaction: losing the caller's other work
        # to a race we expected would be a far worse bug than the race.
        with db.begin_nested():
            db.add(
                RateLimitCounter(
                    scope=scope,
                    subject_hash=digest,
                    window_start=start,
                    hits=1,
                    expires_at=expires_at,
                )
            )
            db.flush()
    except IntegrityError:
        # Someone else created the bucket between our UPDATE and our INSERT, so
        # add to theirs. Exactly one retry: the bucket now provably exists, and
        # a loop here would turn a lost race into a hung request.
        updated = db.execute(
            update(RateLimitCounter)
            .where(
                RateLimitCounter.scope == scope,
                RateLimitCounter.subject_hash == digest,
                RateLimitCounter.window_start == start,
            )
            .values(hits=RateLimitCounter.hits + 1)
            .returning(RateLimitCounter.hits)
        ).scalar_one_or_none()
        return int(updated) if updated is not None else 1
    return 1


def remaining(
    db: Session,
    scope: RateLimitScope,
    signal: str,
    *,
    secret: str,
    now: dt.datetime | None = None,
) -> int:
    """How much budget is left, for tests and for telemetry. Never for a
    response header: §11 keeps `RATE_LIMITED` free of detail, and a countdown
    is detail."""
    budget = BUDGETS[scope]
    moment = now or clock.now()
    start = window_start(moment, budget.window)
    hits = db.execute(
        select(RateLimitCounter.hits).where(
            RateLimitCounter.scope == scope,
            RateLimitCounter.subject_hash == subject_hash(signal, secret=secret),
            RateLimitCounter.window_start == start,
        )
    ).scalar_one_or_none()
    return max(0, budget.limit - int(hits or 0))


def sweep_expired(db: Session, *, now: dt.datetime | None = None) -> int:
    """M17 retention. These rows answer one question about the last few
    minutes and have no reason to outlive it."""
    moment = now or clock.now()
    stale = db.execute(
        select(RateLimitCounter).where(RateLimitCounter.expires_at < moment)
    ).scalars().all()
    for row in stale:
        db.delete(row)
    return len(stale)
