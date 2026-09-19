"""M01 §3.2, §4.7 and §6 AUTH-03/04/08: issuing, validating and ending sessions.

The rule the whole module serves is §4.7: bumping an account's
``authorization_version`` must end every existing session **for any request that
starts after the commit** — "bezbednost ne sme zavisiti od eventualnog outbox
potrošača". So validation reads the account row in the caller's own transaction
and compares versions there. No cache sits between the two, which is the only
arrangement in which M01-QA-021's stale node has no window: there is no second
copy of the answer to be stale.

The outbox event exists too (§13), but for what it is good at — shutting
realtime channels and rebuilding projections. It is propagation, never proof.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domains.identity.auth_enums import (
    AUTHORIZATION_INVALIDATED_EVENT,
    AuthEventOutcome,
    AuthEventType,
    SessionRevokeReason,
    UserAccountStatus,
)
from app.domains.identity.auth_models import (
    AuthenticationEvent,
    AuthIdentity,
    AuthSession,
    UserAccount,
)
from app.platform import clock
from app.platform.outbox.service import enqueue

#: §3.2's fail-closed defaults, used when the deployment has not confirmed its
#: own: "interaktivna aplikaciona sesija prestaje posle 30 minuta neaktivnosti
#: ili na apsolutnom maksimumu od 12 sati, šta pre nastupi."
DEFAULT_IDLE_MINUTES = 30
DEFAULT_ABSOLUTE_HOURS = 12

#: 256 bits from `secrets`. The stored digest is a plain SHA-256 of this, which
#: is safe precisely because the input is random: there is no guessable
#: password behind it for an offline attacker to work through.
_CREDENTIAL_BYTES = 32


def hash_credential(credential: str) -> str:
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


def issue_session(
    db: Session,
    *,
    account: UserAccount,
    identity: AuthIdentity,
    idle_minutes: int = DEFAULT_IDLE_MINUTES,
    absolute_hours: int = DEFAULT_ABSOLUTE_HOURS,
    auth_time: dt.datetime | None = None,
    assurance_context: dict[str, Any] | None = None,
    device_label: str | None = None,
    now: dt.datetime | None = None,
) -> tuple[AuthSession, str]:
    """Create a session and return it with its credential, once.

    The credential is returned rather than stored, and this is the only moment
    it exists in readable form. Callers put it in the cookie and forget it; a
    caller that keeps it has created a second copy of the thing this design
    exists to keep in one place.

    Only ``ACTIVE`` reaches here (§3.1), and the caller has already proven the
    identity — issuing a session is not the place to decide whether one is
    deserved.
    """
    if account.status is not UserAccountStatus.ACTIVE:
        raise ValueError("Only an ACTIVE account may be issued a session (M01 §3.1).")

    moment = now or clock.now()
    credential = secrets.token_urlsafe(_CREDENTIAL_BYTES)
    absolute = moment + dt.timedelta(hours=absolute_hours)
    session = AuthSession(
        credential_hash=hash_credential(credential),
        user_account_id=account.id,
        auth_identity_id=identity.id,
        created_at=moment,
        last_seen_at=moment,
        absolute_expires_at=absolute,
        idle_expires_at=min(moment + dt.timedelta(minutes=idle_minutes), absolute),
        authorization_version_at_issue=account.authorization_version,
        auth_time=auth_time or moment,
        assurance_context=assurance_context or {},
        device_label=device_label,
    )
    db.add(session)
    db.flush()
    return session, credential


def validate_session(
    db: Session,
    credential: str,
    *,
    idle_minutes: int = DEFAULT_IDLE_MINUTES,
    now: dt.datetime | None = None,
) -> tuple[AuthSession, UserAccount] | None:
    """§6 AUTH-03. Runs before every protected command, query, download, export
    and realtime subscribe.

    Returns ``None`` for every failure, without distinguishing them: §11 makes
    ``UNAUTHENTICATED`` say nothing about tenant state, and a caller that could
    tell "expired" from "revoked" from "no such session" would leak which.

    The order matters only in that the account is read last and from the
    database, not from anything that remembered it. That read is what closes
    M01-QA-021's window.
    """
    moment = now or clock.now()
    session = db.execute(
        select(AuthSession).where(AuthSession.credential_hash == hash_credential(credential))
    ).scalar_one_or_none()
    if session is None or not session.is_live(moment):
        return None

    account = db.get(UserAccount, session.user_account_id)
    if account is None or account.status is not UserAccountStatus.ACTIVE:
        return None
    # §4.7. Strict equality, not "at least": a version that somehow went
    # backwards is a corrupted security clock, and the safe reading of a broken
    # clock is "no".
    if session.authorization_version_at_issue != account.authorization_version:
        return None

    _slide(session, moment, idle_minutes)
    return session, account


def _slide(session: AuthSession, now: dt.datetime, idle_minutes: int) -> None:
    """Push the idle deadline out, clamped by the absolute one.

    Clamped, because §3.2 says the session ends at whichever comes first. An
    unclamped slide would let a busy client push the idle window past the
    absolute deadline and turn a hard maximum into a suggestion.
    """
    session.last_seen_at = now
    session.idle_expires_at = min(
        now + dt.timedelta(minutes=idle_minutes), session.absolute_expires_at
    )


def revoke_session(
    db: Session,
    session: AuthSession,
    *,
    reason: SessionRevokeReason,
    now: dt.datetime | None = None,
) -> bool:
    """§6 AUTH-04: end exactly the session presented, and nothing else.

    Returns whether this call was the one that ended it. An already-revoked
    session is left with its original reason and time: the first revocation is
    the one that happened, and overwriting it would lose why.
    """
    if session.revoked_at is not None:
        return False
    session.revoked_at = now or clock.now()
    session.revoke_reason_code = reason
    db.add(
        AuthenticationEvent(
            event_type=AuthEventType.SESSION_REVOKED,
            outcome=AuthEventOutcome.SUCCEEDED,
            user_account_id=session.user_account_id,
            auth_identity_id=session.auth_identity_id,
            reason_code=reason.value,
            occurred_at=session.revoked_at,
        )
    )
    return True


def live_sessions(
    db: Session, account_id: str, *, now: dt.datetime | None = None
) -> list[AuthSession]:
    """Sessions the security UI should show as active (§6 AUTH-Q01, §14)."""
    moment = now or clock.now()
    stmt = select(AuthSession).where(
        AuthSession.user_account_id == account_id,
        AuthSession.revoked_at.is_(None),
    )
    return [s for s in db.execute(stmt).scalars().all() if s.is_live(moment)]


def revoke_account_sessions(
    db: Session,
    account: UserAccount,
    *,
    reason: SessionRevokeReason,
    correlation_id: str | None = None,
    keep_session_id: str | None = None,
    now: dt.datetime | None = None,
) -> int:
    """§6 AUTH-08: the internal port M02/M03/M05/M06/M07/M17 call.

    One transaction: lock the account, bump the version, revoke its sessions,
    write the audit event and the outbox event. The caller commits — the command
    "sme vratiti uspeh tek posle durable commit-a", and a function that committed
    on its own behalf would make that the caller's problem to remember.

    The version bump alone already ends every session, because `validate_session`
    compares against it. Marking the rows too is not redundancy for its own sake:
    it is what lets the security UI say *why* a session ended, and what stops a
    revoked row being re-stamped by a later bump as though it were still live.

    ``keep_session_id`` exists for the one safe case §6 allows — the session that
    performed the action. It is re-stamped with the new version, because a kept
    session carrying the old one would fail its very next request and the "keep"
    would be a lie.
    """
    moment = now or clock.now()
    _lock_account(db, account.id)
    db.refresh(account)

    account.authorization_version += 1
    account.version += 1

    revoked = 0
    for session in live_sessions(db, account.id, now=moment):
        if session.id == keep_session_id:
            session.authorization_version_at_issue = account.authorization_version
            continue
        if revoke_session(db, session, reason=reason, now=moment):
            revoked += 1

    db.add(
        AuthenticationEvent(
            event_type=AuthEventType.AUTHORIZATION_VERSION_BUMPED,
            outcome=AuthEventOutcome.SUCCEEDED,
            user_account_id=account.id,
            reason_code=reason.value,
            correlation_id=correlation_id,
            authorization_version=account.authorization_version,
            occurred_at=moment,
        )
    )
    # §13: PLATFORM scope, `school_id=NULL`, and only opaque ids in the payload.
    # One account can reach many schools, and M01 deliberately does not know
    # which — reading memberships to emit one event per school is the coupling
    # §13 forbids. The platform consumer fans it out.
    enqueue(
        db,
        event_type=AUTHORIZATION_INVALIDATED_EVENT,
        payload={
            "user_account_id": account.id,
            "authorization_version": account.authorization_version,
            "reason_code": reason.value,
            "correlation_id": correlation_id,
            # §13's dedupe key. A dispatcher that receives this twice must do
            # the same thing once.
            "dedupe_key": f"{account.id}:{account.authorization_version}",
        },
        school_id=None,
    )
    return revoked


def _lock_account(db: Session, account_id: str) -> None:
    """Serialize concurrent revocations of one account.

    Without it, two callers can read the same version, both write version+1, and
    one bump is lost — which means one set of sessions silently survives a
    revocation that reported success.
    """
    db.execute(
        text("SELECT 1 FROM user_account WHERE id = :id FOR UPDATE"), {"id": account_id}
    )


def expire_session(
    db: Session, session: AuthSession, *, now: dt.datetime | None = None
) -> None:
    """Mark a session that ran out of time, for the security UI's benefit.

    Bookkeeping, never a guard: the session was already dead the moment its
    deadline passed, because `is_live` compares timestamps rather than reading
    this flag. §5 keeps `EXPIRED` and `REVOKED` distinct so that a list of
    revocations stays a list of security decisions.
    """
    if session.revoked_at is None:
        session.revoked_at = now or clock.now()
        session.revoke_reason_code = SessionRevokeReason.EXPIRED
