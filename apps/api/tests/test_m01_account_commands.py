"""M01 §6 AUTH-05/09/10/11 and §12: account status commands and their receipts.

Security commands break ordinary idempotency in one specific way: the command
can revoke the caller's own session. After `LogoutAll` succeeds, the identical
retry arrives holding a credential that authenticates nothing — and §6 says it
must still get the first result, not a 401 and not a second execution. That is
what `revoked_credential_hash` is for, and it is deliberately narrow: the digest
plus the command plus the same `request_id` open exactly one receipt and
authorize nothing else.

AUTH-09/10/11 are tested as ports. §6 requires an M05 permission for each, M05
does not exist yet, and a route that checked a permission this codebase invented
would look like the contract was met when it was not.
"""

from __future__ import annotations

import uuid

import pytest
from app.common.errors import (
    IdempotencyInProgressError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyReusedError,
    InvalidAccountTransitionError,
    StaleVersionError,
)
from app.domains.identity import auth_commands, sessions
from app.domains.identity.accounts import create_account_with_identity
from app.domains.identity.auth_enums import (
    GOOGLE_ISSUER,
    GOOGLE_PROVIDER,
    AccountDisableReason,
    AccountSuspendReason,
    AuthCommand,
    AuthCommandReceiptStatus,
    SessionRevokeReason,
    UserAccountStatus,
)
from app.domains.identity.auth_models import (
    AuthCommandReceipt,
    AuthenticationEvent,
    AuthIdentity,
    UserAccount,
)
from app.platform.outbox.models import OutboxMessage
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.factories import make_person


def _account(db: Session, subject: str = "sub-cmd") -> tuple[UserAccount, AuthIdentity]:
    person = make_person(db, given="C", family=subject[-4:])
    account, identity = create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
    )
    db.commit()
    return account, identity


def _rid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# §12 — the request id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "not-a-uuid", "12345"])
def test_a_request_id_must_be_a_uuid(value: str) -> None:
    """M01-QA-027, and §12's reason for checking first: a bad key must produce
    no business write, no success audit, no receipt and no outbox message, and
    only a check made before any of them can promise that."""
    with pytest.raises(IdempotencyKeyInvalidError):
        auth_commands.require_request_id(value)


def test_the_header_must_equal_the_body(db: Session) -> None:
    """§12: on HTTP the `Idempotency-Key` header and the body `request_id` are
    one value in two places. Two values would mean two answers to "which
    request is this"."""
    rid = _rid()
    assert auth_commands.require_request_id(rid, rid) == rid
    with pytest.raises(IdempotencyKeyInvalidError):
        auth_commands.require_request_id(rid, str(uuid.uuid4()))


def test_an_absent_header_is_allowed_off_http() -> None:
    """The header requirement is a transport rule. An internal caller has no
    headers, and inventing one for it would be ceremony, not safety."""
    rid = _rid()
    assert auth_commands.require_request_id(rid, None) == rid


def test_payload_hash_ignores_key_order() -> None:
    """Otherwise a client whose dict serializes differently on retry would be
    told it changed the request."""
    a = auth_commands.canonical_payload_hash({"x": 1, "y": 2})
    b = auth_commands.canonical_payload_hash({"y": 2, "x": 1})
    assert a == b
    assert a != auth_commands.canonical_payload_hash({"x": 1, "y": 3})


# ---------------------------------------------------------------------------
# §12 — the receipt
# ---------------------------------------------------------------------------


def test_a_completed_receipt_replays(db: Session) -> None:
    account, _ = _account(db, "sub-replay")
    rid = _rid()
    receipt = auth_commands.begin(
        db,
        account_id=account.id,
        command=AuthCommand.LOGOUT_ALL,
        request_id=rid,
        payload={"a": 1},
    )
    assert receipt.replay is None
    auth_commands.complete(db, receipt, status=200, body={"revoked_sessions": 3})
    db.commit()

    again = auth_commands.begin(
        db,
        account_id=account.id,
        command=AuthCommand.LOGOUT_ALL,
        request_id=rid,
        payload={"a": 1},
    )
    assert again.replay == {"status": 200, "body": {"revoked_sessions": 3}}


def test_the_same_key_with_a_different_payload_is_refused(db: Session) -> None:
    """§11 `IDEMPOTENCY_KEY_REUSED`. Serving the first result here would hide a
    client bug: the same key naming two different requests."""
    account, _ = _account(db, "sub-reused")
    rid = _rid()
    receipt = auth_commands.begin(
        db,
        account_id=account.id,
        command=AuthCommand.SUSPEND_ACCOUNT,
        request_id=rid,
        payload={"reason": "A"},
    )
    auth_commands.complete(db, receipt, status=200, body={})
    db.commit()

    with pytest.raises(IdempotencyKeyReusedError):
        auth_commands.begin(
            db,
            account_id=account.id,
            command=AuthCommand.SUSPEND_ACCOUNT,
            request_id=rid,
            payload={"reason": "B"},
        )


def test_an_unfinished_receipt_is_in_progress_not_a_replay(db: Session) -> None:
    """M01-QA-026: the second caller waits, and above all does not execute the
    side effect again."""
    account, _ = _account(db, "sub-inflight")
    rid = _rid()
    auth_commands.begin(
        db,
        account_id=account.id,
        command=AuthCommand.LOGOUT_ALL,
        request_id=rid,
        payload={"a": 1},
    )
    db.commit()

    with pytest.raises(IdempotencyInProgressError) as caught:
        auth_commands.begin(
            db,
            account_id=account.id,
            command=AuthCommand.LOGOUT_ALL,
            request_id=rid,
            payload={"a": 1},
        )
    assert caught.value.headers["Retry-After"] == "1"


def test_an_unfinished_receipt_cannot_carry_a_result(db: Session) -> None:
    """A crash mid-command must not leave a row that replays `null` as though
    it were the answer."""
    account, _ = _account(db, "sub-halfrow")
    db.add(
        AuthCommandReceipt(
            user_account_id=account.id,
            command=AuthCommand.LOGOUT_ALL,
            request_id=_rid(),
            payload_hash="x" * 64,
            status=AuthCommandReceiptStatus.IN_PROGRESS,
            response_status=200,
            retain_until=sessions.clock.now(),
        )
    )
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_receipts_are_scoped_per_account(db: Session) -> None:
    """One `request_id` from two accounts is two commands. Sharing a scope would
    let one account's retry collect another's result."""
    first, _ = _account(db, "sub-scope-1")
    second, _ = _account(db, "sub-scope-2")
    rid = _rid()
    for account in (first, second):
        receipt = auth_commands.begin(
            db,
            account_id=account.id,
            command=AuthCommand.LOGOUT_ALL,
            request_id=rid,
            payload={},
        )
        assert receipt.replay is None
        auth_commands.complete(db, receipt, status=200, body={"who": account.id})
    db.commit()
    assert db.execute(select(func.count()).select_from(AuthCommandReceipt)).scalar_one() == 2


# ---------------------------------------------------------------------------
# §6 AUTH-05
# ---------------------------------------------------------------------------


def test_logout_all_ends_every_session_including_its_own(db: Session) -> None:
    """M01-QA-009. The current session is not kept: §6 allows keeping one only
    for a proven-safe scenario, and "log me out everywhere" is its opposite."""
    account, identity = _account(db, "sub-logoutall")
    _, current = sessions.issue_session(db, account=account, identity=identity)
    _, other = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    result = auth_commands.logout_all(
        db, account=account, request_id=_rid(), current_credential=current
    )
    db.commit()

    assert result["body"]["revoked_sessions"] == 2
    assert sessions.validate_session(db, current) is None
    assert sessions.validate_session(db, other) is None


def test_the_retry_after_self_revocation_gets_the_first_result(db: Session) -> None:
    """M01-QA-020, the scenario this whole table exists for.

    The retry presents a credential that authenticates nothing. It still gets
    the first result — and, importantly, no session comes back to life.
    """
    account, identity = _account(db, "sub-retry")
    _, current = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    rid = _rid()

    first = auth_commands.logout_all(
        db, account=account, request_id=rid, current_credential=current
    )
    db.commit()

    retry = auth_commands.logout_all(
        db, account=account, request_id=rid, current_credential=current
    )
    assert retry == first
    assert sessions.validate_session(db, current) is None


def test_the_revoked_credential_opens_only_its_own_receipt(db: Session) -> None:
    """§6: "to nije autorizacija ni za jednu drugu radnju."

    A different command, or a different request id, finds nothing — the digest
    is a key to one stored result, not a second credential.
    """
    account, identity = _account(db, "sub-narrow")
    _, current = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    rid = _rid()
    auth_commands.logout_all(
        db, account=account, request_id=rid, current_credential=current
    )
    db.commit()

    assert auth_commands.replay_for_revoked_credential(
        db, credential=current, command=AuthCommand.LOGOUT_ALL, request_id=rid
    ) is not None
    assert auth_commands.replay_for_revoked_credential(
        db, credential=current, command=AuthCommand.DISABLE_ACCOUNT, request_id=rid
    ) is None
    assert auth_commands.replay_for_revoked_credential(
        db, credential=current, command=AuthCommand.LOGOUT_ALL, request_id=_rid()
    ) is None


def test_logout_all_over_http(client: TestClient, db: Session) -> None:
    resp = client.post(
        "/auth/password/register",
        json={
            "email": "sve@example.invalid",
            "password": "dovoljnodugo1",
            "given_name": "S",
            "family_name": "V",
        },
    )
    assert resp.status_code == 200
    rid = _rid()

    out = client.post(
        "/auth/logout-all",
        json={"request_id": rid},
        headers={"Idempotency-Key": rid},
    )
    assert out.status_code == 200
    assert out.json()["revoked_sessions"] == 1
    assert db.execute(select(func.count()).select_from(AuthCommandReceipt)).scalar_one() == 1


def test_logout_all_rejects_a_mismatched_key(client: TestClient) -> None:
    """M01-QA-027: 400 and no business write."""
    client.post(
        "/auth/password/register",
        json={
            "email": "kljuc@example.invalid",
            "password": "dovoljnodugo1",
            "given_name": "K",
            "family_name": "L",
        },
    )
    resp = client.post(
        "/auth/logout-all",
        json={"request_id": _rid()},
        headers={"Idempotency-Key": _rid()},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_INVALID"


def test_logout_all_without_a_session_is_unauthenticated(client: TestClient) -> None:
    rid = _rid()
    resp = client.post(
        "/auth/logout-all",
        json={"request_id": rid},
        headers={"Idempotency-Key": rid},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# §6 AUTH-09 / AUTH-10 / AUTH-11
# ---------------------------------------------------------------------------


def test_suspend_revokes_everything_and_bumps(db: Session) -> None:
    """M01-QA-023, first half."""
    account, identity = _account(db, "sub-suspend")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    version_before = account.authorization_version

    result = auth_commands.suspend_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountSuspendReason.SUSPECTED_COMPROMISE,
        request_id=_rid(),
    )
    db.commit()

    assert result["body"]["status"] == "SUSPENDED"
    assert account.authorization_version > version_before
    assert sessions.validate_session(db, credential) is None


def test_reactivate_does_not_bring_old_sessions_back(db: Session) -> None:
    """M01-QA-023, second half. §6 AUTH-10 is explicit: reactivation "ne vraća
    stare sesije i ne prijavljuje korisnika automatski"."""
    account, identity = _account(db, "sub-react")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    auth_commands.suspend_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountSuspendReason.BILLING_HOLD,
        request_id=_rid(),
    )
    db.commit()
    auth_commands.reactivate_account(
        db, account=account, expected_version=account.version, request_id=_rid()
    )
    db.commit()

    assert account.status is UserAccountStatus.ACTIVE
    assert sessions.validate_session(db, credential) is None


def test_reactivate_needs_a_way_back_in(db: Session) -> None:
    """§6 AUTH-10: only if at least one identity is still linked. Reactivating
    an account with no way to sign in produces a live account nobody can use and
    an operator who thinks the problem is fixed."""
    account, identity = _account(db, "sub-noident")
    auth_commands.suspend_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountSuspendReason.ABUSE_UNDER_REVIEW,
        request_id=_rid(),
    )
    db.commit()

    identity.unlinked_at = sessions.clock.now()
    identity.unlink_reason_code = "SECURITY_INCIDENT"
    db.commit()

    with pytest.raises(InvalidAccountTransitionError):
        auth_commands.reactivate_account(
            db, account=account, expected_version=account.version, request_id=_rid()
        )


def test_a_disabled_account_cannot_be_reactivated(db: Session) -> None:
    """M01-QA-024: §5's table has no row out of `DISABLED`, and asking gets
    `INVALID_ACCOUNT_TRANSITION` rather than a quiet no-op."""
    account, _ = _account(db, "sub-nodisable")
    auth_commands.disable_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountDisableReason.LEGAL_REQUEST,
        request_id=_rid(),
    )
    db.commit()

    with pytest.raises(InvalidAccountTransitionError):
        auth_commands.reactivate_account(
            db, account=account, expected_version=account.version, request_id=_rid()
        )
    db.rollback()
    assert account.status is UserAccountStatus.DISABLED


def test_suspending_a_suspended_account_is_refused(db: Session) -> None:
    account, _ = _account(db, "sub-twice-susp")
    auth_commands.suspend_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountSuspendReason.BILLING_HOLD,
        request_id=_rid(),
    )
    db.commit()

    with pytest.raises(InvalidAccountTransitionError):
        auth_commands.suspend_account(
            db,
            account=account,
            expected_version=account.version,
            reason_code=AccountSuspendReason.BILLING_HOLD,
            request_id=_rid(),
        )


def test_a_stale_expected_version_is_refused(db: Session) -> None:
    """§11 `STALE_VERSION`. The administrator is acting on a screen that no
    longer describes the account."""
    account, _ = _account(db, "sub-stale")
    with pytest.raises(StaleVersionError):
        auth_commands.suspend_account(
            db,
            account=account,
            expected_version=account.version + 99,
            reason_code=AccountSuspendReason.BILLING_HOLD,
            request_id=_rid(),
        )


def test_disable_records_when_and_why(db: Session) -> None:
    """§3.1 pairs the stamp with the status, and §11 keeps the reason out of the
    user's response — so the audit trail is the only place it survives."""
    account, _ = _account(db, "sub-why")
    auth_commands.disable_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountDisableReason.SECURITY_INCIDENT,
        request_id=_rid(),
        correlation_id="corr-disable",
    )
    db.commit()

    assert account.disabled_at is not None
    assert account.disabled_reason_code is AccountDisableReason.SECURITY_INCIDENT
    events = db.execute(
        select(AuthenticationEvent).where(
            AuthenticationEvent.event_type == "auth.account_disabled"
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].reason_code == "SECURITY_INCIDENT"
    assert events[0].correlation_id == "corr-disable"


def test_reactivation_clears_the_disable_stamp(db: Session) -> None:
    """§3.1's CHECK would refuse a live account still carrying one — which is
    the database making sure the two can never disagree."""
    account, _ = _account(db, "sub-clear")
    auth_commands.suspend_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountSuspendReason.BILLING_HOLD,
        request_id=_rid(),
    )
    db.commit()
    auth_commands.reactivate_account(
        db, account=account, expected_version=account.version, request_id=_rid()
    )
    db.commit()
    assert account.disabled_at is None and account.disabled_reason_code is None


def test_a_status_command_emits_exactly_one_invalidation(db: Session) -> None:
    """§13, and M01-QA-028: one PLATFORM event, not one per school."""
    account, identity = _account(db, "sub-oneevent")
    sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    auth_commands.suspend_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountSuspendReason.SUSPECTED_COMPROMISE,
        request_id=_rid(),
    )
    db.commit()

    messages = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.event_type == "identity.authorization_invalidated"
        )
    ).scalars().all()
    assert len(messages) == 1
    assert messages[0].school_id is None


def test_a_replayed_status_command_changes_nothing_twice(db: Session) -> None:
    """The receipt is claimed before the state change, so a retry cannot walk
    the account through the transition a second time.

    A genuine retry resends the *identical* request, `expected_version`
    included — that is what makes it a retry rather than a new command.
    """
    account, _ = _account(db, "sub-replay-status")
    rid = _rid()
    sent_version = account.version
    first = auth_commands.suspend_account(
        db,
        account=account,
        expected_version=sent_version,
        reason_code=AccountSuspendReason.BILLING_HOLD,
        request_id=rid,
    )
    db.commit()
    version_after = account.authorization_version

    second = auth_commands.suspend_account(
        db,
        account=account,
        expected_version=sent_version,
        reason_code=AccountSuspendReason.BILLING_HOLD,
        request_id=rid,
    )
    db.commit()
    assert second == first
    assert account.authorization_version == version_after


def test_retrying_with_a_refreshed_version_is_a_new_request(db: Session) -> None:
    """And is refused, which is the behaviour §12 wants rather than a quirk.

    `expected_version` is part of the request, so changing it changes the
    request. A client that reloaded the account and wants to act on what it now
    sees is making a *new* decision, and it needs a new key to say so — the
    alternative is that the first result is served for a request nobody made.
    """
    account, _ = _account(db, "sub-refreshed")
    rid = _rid()
    auth_commands.suspend_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountSuspendReason.BILLING_HOLD,
        request_id=rid,
    )
    db.commit()

    with pytest.raises(IdempotencyKeyReusedError):
        auth_commands.suspend_account(
            db,
            account=account,
            expected_version=account.version,
            reason_code=AccountSuspendReason.BILLING_HOLD,
            request_id=rid,
        )


def test_sessions_revoked_by_a_suspension_say_so(db: Session) -> None:
    """Which is the point of a closed reason vocabulary: a security reviewer
    months later can tell a suspension from a logout."""
    account, identity = _account(db, "sub-reasoncode")
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    auth_commands.suspend_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountSuspendReason.SUSPECTED_COMPROMISE,
        request_id=_rid(),
    )
    db.commit()
    assert session.revoke_reason_code is SessionRevokeReason.ACCOUNT_SUSPENDED
