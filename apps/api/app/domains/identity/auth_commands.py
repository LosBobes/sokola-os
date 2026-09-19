"""M01 §6 AUTH-05/09/10/11 and §12: the account status commands and their receipts.

Two things make these different from ordinary idempotent writes, and both are
why they have their own receipt table rather than reusing
``app.platform.idempotency``:

* they are **account-scoped, not school-scoped**. One account reaches many
  schools, and §8 keeps tenancy off the authentication path entirely;
* they can **revoke the caller's own session**. §6 AUTH-05 spells out the
  consequence: after success, the identical retry arrives holding a credential
  that no longer authenticates anything, and it must still receive the first
  result rather than a 401 or a second execution.

AUTH-09/10/11 are exposed here as ports, not HTTP routes. §6 requires an M05
permission (`platform.accounts.suspend` and siblings) for each, and M05's
permission registry does not exist yet. A route that checked nothing, or
checked a permission this codebase invented, would be worse than no route: it
would look like the contract had been satisfied.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import (
    IdempotencyInProgressError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyReusedError,
    InvalidAccountTransitionError,
    StaleVersionError,
)
from app.domains.identity import sessions
from app.domains.identity.auth_enums import (
    AccountDisableReason,
    AccountSuspendReason,
    AuthCommand,
    AuthCommandReceiptStatus,
    AuthEventOutcome,
    AuthEventType,
    SessionRevokeReason,
    UserAccountStatus,
)
from app.domains.identity.auth_models import (
    AuthCommandReceipt,
    AuthenticationEvent,
    AuthIdentity,
    AuthSession,
    UserAccount,
)
from app.platform import clock

#: §12: a receipt outlives "maksimalna session+retry granica". The session's own
#: absolute maximum is 12 hours (§3.2); a week is comfortably past any retry a
#: real client will make, and keeping it longer costs one small row.
RECEIPT_RETENTION_DAYS = 7


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    """§12's "kanonski payload". Key order must not change the hash, or a client
    that serializes its dict differently on retry would be told it changed the
    request."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def require_request_id(request_id: str, header_value: str | None = None) -> str:
    """§12: a stable UUID, and on HTTP the `Idempotency-Key` header must equal it.

    Checked before anything else happens, because §12 requires that a bad pair
    produce no business write, no success audit, no receipt and no outbox
    message (M01-QA-027). A check performed later could not promise that.
    """
    try:
        parsed = uuid.UUID(str(request_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise IdempotencyKeyInvalidError(
            "Zahtev mora imati važeći `request_id` (UUID)."
        ) from exc
    if header_value is not None and str(header_value).strip() != str(request_id):
        raise IdempotencyKeyInvalidError(
            "`Idempotency-Key` se ne poklapa sa `request_id` u telu zahteva."
        )
    return str(parsed)


@dataclass(slots=True)
class Receipt:
    """A started command, or the durable result of one that already ran."""

    record: AuthCommandReceipt
    replay: dict[str, Any] | None


def begin(
    db: Session,
    *,
    account_id: str,
    command: AuthCommand,
    request_id: str,
    payload: dict[str, Any],
    now: dt.datetime | None = None,
) -> Receipt:
    """Claim ``(account, command, request_id)`` or hand back what it produced.

    Three outcomes, all from §12: a completed receipt replays; a receipt whose
    payload differs is ``IDEMPOTENCY_KEY_REUSED``; one still running is
    ``IDEMPOTENCY_IN_PROGRESS`` with ``Retry-After: 1`` and no second side
    effect (M01-QA-026).
    """
    moment = now or clock.now()
    payload_hash = canonical_payload_hash(payload)
    existing = _find(db, account_id, command, request_id)
    if existing is not None:
        return Receipt(record=existing, replay=_replay_of(existing, payload_hash))

    record = AuthCommandReceipt(
        user_account_id=account_id,
        command=command,
        request_id=request_id,
        payload_hash=payload_hash,
        status=AuthCommandReceiptStatus.IN_PROGRESS,
        retain_until=moment + dt.timedelta(days=RECEIPT_RETENTION_DAYS),
    )
    db.add(record)
    try:
        # The unique constraint settles a genuine race: whoever inserts first
        # owns the command, and the loser is told to retry rather than running
        # the same revocation again.
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise IdempotencyInProgressError(
            "Ista komanda sa ovim ključem je već u toku."
        ) from exc
    return Receipt(record=record, replay=None)


def _replay_of(
    record: AuthCommandReceipt, payload_hash: str
) -> dict[str, Any]:
    if record.payload_hash != payload_hash:
        raise IdempotencyKeyReusedError(
            "Isti ključ je već korišćen sa drugačijim podacima."
        )
    if record.status is not AuthCommandReceiptStatus.COMPLETED:
        raise IdempotencyInProgressError("Ista komanda sa ovim ključem je već u toku.")
    return {"status": record.response_status, "body": record.response_body}


def complete(
    db: Session,
    receipt: Receipt,
    *,
    status: int,
    body: dict[str, Any],
    revoked_credential_hash: str | None = None,
) -> dict[str, Any]:
    """Store the result in the same transaction as the change it describes.

    ``revoked_credential_hash`` is how §6 AUTH-05's retry finds this row after
    the command logged its own caller out. It is set only by the command that
    revoked that exact credential, so the digest opens one receipt and nothing
    else.
    """
    receipt.record.status = AuthCommandReceiptStatus.COMPLETED
    receipt.record.response_status = status
    receipt.record.response_body = body
    receipt.record.revoked_credential_hash = revoked_credential_hash
    db.flush()
    return {"status": status, "body": body}


def replay_for_revoked_credential(
    db: Session, *, credential: str, command: AuthCommand, request_id: str
) -> dict[str, Any] | None:
    """§6 AUTH-05: the retry path for a caller whose session this command ended.

    Deliberately narrow. It needs the credential, the command *and* the same
    ``request_id``, and returns a stored result — never a session, a principal
    or permission to do anything further. §6: "to nije autorizacija ni za jednu
    drugu radnju."
    """
    digest = sessions.hash_credential(credential)
    record = db.execute(
        select(AuthCommandReceipt).where(
            AuthCommandReceipt.revoked_credential_hash == digest,
            AuthCommandReceipt.command == command,
            AuthCommandReceipt.request_id == request_id,
            AuthCommandReceipt.status == AuthCommandReceiptStatus.COMPLETED,
        )
    ).scalar_one_or_none()
    if record is None:
        return None
    return {"status": record.response_status, "body": record.response_body}


def _find(
    db: Session, account_id: str, command: AuthCommand, request_id: str
) -> AuthCommandReceipt | None:
    return db.execute(
        select(AuthCommandReceipt).where(
            AuthCommandReceipt.user_account_id == account_id,
            AuthCommandReceipt.command == command,
            AuthCommandReceipt.request_id == request_id,
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# AUTH-05 LogoutAll
# ---------------------------------------------------------------------------


def logout_all(
    db: Session,
    *,
    account: UserAccount,
    request_id: str,
    current_credential: str | None = None,
    correlation_id: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """§6 AUTH-05: end every session of this account, including this one.

    The receipt is written **before** the version bump and in the same
    transaction, which is the ordering §6 asks for: it is what lets the retry
    that arrives holding the now-revoked credential still be answered.

    The current session is not kept. §6 allows keeping one only for a "dokazano
    bezbedan scenario", and "the user asked to be logged out everywhere" is the
    opposite of that.
    """
    moment = now or clock.now()
    payload = {"account_id": account.id, "command": AuthCommand.LOGOUT_ALL.value}

    if current_credential is not None:
        replay = replay_for_revoked_credential(
            db,
            credential=current_credential,
            command=AuthCommand.LOGOUT_ALL,
            request_id=request_id,
        )
        if replay is not None:
            return replay

    receipt = begin(
        db,
        account_id=account.id,
        command=AuthCommand.LOGOUT_ALL,
        request_id=request_id,
        payload=payload,
        now=moment,
    )
    if receipt.replay is not None:
        return receipt.replay

    revoked = sessions.revoke_account_sessions(
        db,
        account,
        reason=SessionRevokeReason.LOGOUT_ALL,
        correlation_id=correlation_id,
        now=moment,
    )
    db.add(
        AuthenticationEvent(
            event_type=AuthEventType.LOGOUT_ALL,
            outcome=AuthEventOutcome.SUCCEEDED,
            user_account_id=account.id,
            correlation_id=correlation_id,
            authorization_version=account.authorization_version,
            occurred_at=moment,
        )
    )
    return complete(
        db,
        receipt,
        status=200,
        # Minimal, per §6 AUTH-Q01's spirit: enough for the UI to confirm, and
        # nothing about other sessions, devices or schools.
        body={"revoked_sessions": revoked},
        revoked_credential_hash=(
            sessions.hash_credential(current_credential) if current_credential else None
        ),
    )


# ---------------------------------------------------------------------------
# AUTH-09 / AUTH-10 / AUTH-11 — administrative status changes
# ---------------------------------------------------------------------------


def suspend_account(
    db: Session,
    *,
    account: UserAccount,
    expected_version: int,
    reason_code: AccountSuspendReason,
    request_id: str,
    correlation_id: str | None = None,
    actor_user_account_id: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """§6 AUTH-09. ``ACTIVE → SUSPENDED`` only.

    The caller must already have proven M05's `platform.accounts.suspend`; this
    port does not check it, because there is no registry yet to check against
    and a permission this module invented would be a permission nobody granted.
    """
    return _transition(
        db,
        account=account,
        command=AuthCommand.SUSPEND_ACCOUNT,
        expected_version=expected_version,
        allowed_from=(UserAccountStatus.ACTIVE,),
        to_status=UserAccountStatus.SUSPENDED,
        reason_code=reason_code.value,
        revoke_reason=SessionRevokeReason.ACCOUNT_SUSPENDED,
        event_type=AuthEventType.ACCOUNT_SUSPENDED,
        request_id=request_id,
        correlation_id=correlation_id,
        actor_user_account_id=actor_user_account_id,
        now=now,
    )


def reactivate_account(
    db: Session,
    *,
    account: UserAccount,
    expected_version: int,
    request_id: str,
    correlation_id: str | None = None,
    actor_user_account_id: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """§6 AUTH-10. ``SUSPENDED → ACTIVE``, and only with a linked identity left.

    Reactivation does not return the old sessions and does not sign anyone in:
    the version is bumped precisely so nothing issued before the suspension
    comes back to life. Someone reactivated has to log in again, which is also
    the only way to prove they are still who held the account.

    `DISABLED` and `MERGED_RETIRED` never come back through here (§5 has no row
    out of either), and asking gets `INVALID_ACCOUNT_TRANSITION` rather than a
    quiet refusal.
    """
    if not _has_linked_identity(db, account.id):
        raise InvalidAccountTransitionError(
            "Nalog nema nijedan aktivan način prijave."
        )
    return _transition(
        db,
        account=account,
        command=AuthCommand.REACTIVATE_ACCOUNT,
        expected_version=expected_version,
        allowed_from=(UserAccountStatus.SUSPENDED,),
        to_status=UserAccountStatus.ACTIVE,
        reason_code="REACTIVATED",
        revoke_reason=SessionRevokeReason.ACCESS_CHANGED,
        event_type=AuthEventType.AUTHORIZATION_VERSION_BUMPED,
        request_id=request_id,
        correlation_id=correlation_id,
        actor_user_account_id=actor_user_account_id,
        now=now,
    )


def disable_account(
    db: Session,
    *,
    account: UserAccount,
    expected_version: int,
    reason_code: AccountDisableReason,
    request_id: str,
    correlation_id: str | None = None,
    actor_user_account_id: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """§6 AUTH-11. ``ACTIVE|SUSPENDED → DISABLED``, terminal in the ordinary flow.

    Requires M05's `platform.accounts.disable` plus an M17 legal/security guard,
    neither of which exists yet — see this module's docstring. The audit history
    is kept in full: §6 removes the ability to sign in, never the record.
    """
    return _transition(
        db,
        account=account,
        command=AuthCommand.DISABLE_ACCOUNT,
        expected_version=expected_version,
        allowed_from=(UserAccountStatus.ACTIVE, UserAccountStatus.SUSPENDED),
        to_status=UserAccountStatus.DISABLED,
        reason_code=reason_code.value,
        revoke_reason=SessionRevokeReason.ACCOUNT_DISABLED,
        event_type=AuthEventType.ACCOUNT_DISABLED,
        request_id=request_id,
        correlation_id=correlation_id,
        actor_user_account_id=actor_user_account_id,
        now=now,
    )


def _transition(
    db: Session,
    *,
    account: UserAccount,
    command: AuthCommand,
    expected_version: int,
    allowed_from: tuple[UserAccountStatus, ...],
    to_status: UserAccountStatus,
    reason_code: str,
    revoke_reason: SessionRevokeReason,
    event_type: AuthEventType,
    request_id: str,
    correlation_id: str | None,
    actor_user_account_id: str | None,
    now: dt.datetime | None,
) -> dict[str, Any]:
    """The shape §6 gives all three status commands.

    One transaction: check the transition, check the version, change the status,
    bump the authorization version, revoke every session, audit, outbox, store
    the receipt. The caller commits, because §6 lets these report success only
    after a durable commit and a function that committed for itself would take
    that decision away.

    The order is not arbitrary. The receipt is claimed *before* the state change
    so a concurrent identical request loses the race on the unique constraint
    rather than half-way through the revocation.
    """
    moment = now or clock.now()
    payload = {
        "account_id": account.id,
        "command": command.value,
        "to_status": to_status.value,
        "reason_code": reason_code,
        "expected_version": expected_version,
    }
    receipt = begin(
        db,
        account_id=account.id,
        command=command,
        request_id=request_id,
        payload=payload,
        now=moment,
    )
    if receipt.replay is not None:
        return receipt.replay

    # Lock and re-read before deciding anything, so the transition and version
    # checks below are made against the row as it is now rather than as it was
    # when the request handler first loaded it.
    sessions.lock_account(db, account.id)
    db.refresh(account)

    if account.status not in allowed_from:
        raise InvalidAccountTransitionError(
            "Tražena promena statusa nije dozvoljena iz trenutnog stanja."
        )
    if account.version != expected_version:
        raise StaleVersionError("Osvežite bezbednosno stanje i pokušajte ponovo.")

    account.status = to_status
    if to_status is UserAccountStatus.DISABLED:
        account.disabled_at = moment
        account.disabled_reason_code = AccountDisableReason(reason_code)
    elif to_status is UserAccountStatus.ACTIVE:
        # §3.1's CHECK pairs the stamp with the status; a reactivated account
        # that kept a disable stamp would be a row the database refuses, and
        # rightly so.
        account.disabled_at = None
        account.disabled_reason_code = None

    revoked = sessions.revoke_account_sessions(
        db,
        account,
        reason=revoke_reason,
        correlation_id=correlation_id,
        lock=False,
        now=moment,
    )
    db.add(
        AuthenticationEvent(
            event_type=event_type,
            outcome=AuthEventOutcome.SUCCEEDED,
            user_account_id=account.id,
            reason_code=reason_code,
            correlation_id=correlation_id,
            authorization_version=account.authorization_version,
            occurred_at=moment,
        )
    )
    return complete(
        db,
        receipt,
        status=200,
        body={
            "status": account.status.value,
            "version": account.version,
            "revoked_sessions": revoked,
        },
    )


def _has_linked_identity(db: Session, account_id: str) -> bool:
    return (
        db.execute(
            select(AuthIdentity.id).where(
                AuthIdentity.user_account_id == account_id,
                AuthIdentity.unlinked_at.is_(None),
            )
        ).first()
        is not None
    )


def sweep_expired_receipts(db: Session, *, now: dt.datetime | None = None) -> int:
    """Housekeeping, not a guard. §12 sets a floor on how long a receipt is
    kept; nothing reads `retain_until` to decide whether a replay is valid."""
    moment = now or clock.now()
    stale = db.execute(
        select(AuthCommandReceipt).where(AuthCommandReceipt.retain_until < moment)
    ).scalars().all()
    for record in stale:
        db.delete(record)
    return len(stale)


def find_session_by_credential(db: Session, credential: str) -> AuthSession | None:
    """Convenience for transports that hold a credential and need its row."""
    return db.execute(
        select(AuthSession).where(
            AuthSession.credential_hash == sessions.hash_credential(credential)
        )
    ).scalar_one_or_none()
