"""M01 §3.2, §4.7, §6 AUTH-03/04/08: sessions that can actually be ended.

The previous session was a signed cookie carrying a person id. It had no server
row, so there was nothing to revoke: "log me out everywhere" could not be
written, and a cookie issued on a borrowed laptop stayed valid until its
signature aged out no matter what happened to the account in between.

The invariant everything below circles is §4.7 — a bump of
``authorization_version`` ends every session of that account for any request
starting after the commit, and *"bezbednost ne sme zavisiti od eventualnog
outbox potrošača"*. So validation reads the account in the caller's own
transaction and compares versions there. The outbox event is emitted too, but
for propagation; it is never the thing that says no.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import UnauthorizedError
from app.config import get_settings
from app.domains.identity import sessions
from app.domains.identity.accounts import create_account_with_identity, find_identity
from app.domains.identity.auth_enums import (
    AUTHORIZATION_INVALIDATED_EVENT,
    GOOGLE_ISSUER,
    GOOGLE_PROVIDER,
    AccountDisableReason,
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
from app.platform.outbox.models import OutboxMessage
from app.security.auth import SESSION_CREDENTIAL_KEY, resolve_principal
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.requests import Request

from tests.factories import make_person


def _signed_in(
    db: Session, *, subject: str = "sub-session"
) -> tuple[UserAccount, AuthIdentity]:
    person = make_person(db, given="S", family=subject[-4:])
    account, identity = create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
    )
    db.commit()
    return account, identity


def _request(credential: str | None) -> Request:
    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("test", 80),
        "session": {SESSION_CREDENTIAL_KEY: credential} if credential else {},
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# §3.2 — what a session is
# ---------------------------------------------------------------------------


def test_the_credential_is_never_stored(db: Session) -> None:
    """Only its digest is. A copy of the database yields no working sessions,
    which is the difference between leaking a session table and leaking every
    live login."""
    account, identity = _signed_in(db, subject="sub-digest")
    session, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    assert session.credential_hash != credential
    assert session.credential_hash == sessions.hash_credential(credential)
    stored = set(db.execute(select(AuthSession.credential_hash)).scalars().all())
    assert credential not in stored


def test_session_id_is_not_time_sortable(db: Session) -> None:
    """§3.2 asks for an unpredictable id. The repo's usual ULID is time-ordered,
    which narrows a guess to its random half, so sessions use a fully random one
    and give up the index locality."""
    account, identity = _signed_in(db, subject="sub-idshape")
    first, _ = sessions.issue_session(db, account=account, identity=identity)
    second, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    assert first.id.startswith("ses_") and second.id.startswith("ses_")
    # Two ULIDs minted in the same millisecond share a long common prefix; two
    # random ids do not.
    body_a, body_b = first.id[4:], second.id[4:]
    assert body_a[:6] != body_b[:6]


def test_defaults_are_thirty_minutes_idle_and_twelve_hours_absolute(
    db: Session,
) -> None:
    """§3.2's fail-closed defaults, asserted rather than assumed — the spec
    calls them "strukturirana bezbednosna konfiguracija, ne dokumentaciona
    pretpostavka"."""
    account, identity = _signed_in(db, subject="sub-defaults")
    now = clock.now()
    session, _ = sessions.issue_session(db, account=account, identity=identity, now=now)
    db.commit()

    assert session.idle_expires_at == now + dt.timedelta(minutes=30)
    assert session.absolute_expires_at == now + dt.timedelta(hours=12)
    settings = get_settings()
    assert settings.session_idle_minutes == 30
    assert settings.session_absolute_hours == 12


def test_idle_window_is_clamped_by_the_absolute_one(db: Session) -> None:
    """An idle window longer than the absolute lifetime would make the absolute
    deadline advisory, and §3.2 says whichever comes *first*."""
    account, identity = _signed_in(db, subject="sub-clamp")
    session, _ = sessions.issue_session(
        db, account=account, identity=identity, idle_minutes=600, absolute_hours=1
    )
    db.commit()
    assert session.idle_expires_at == session.absolute_expires_at


def test_a_session_may_not_outlive_its_absolute_deadline(db: Session) -> None:
    """And the database says so too, not only the code that writes it."""
    account, identity = _signed_in(db, subject="sub-ckclamp")
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    session.idle_expires_at = session.absolute_expires_at + dt.timedelta(minutes=1)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_only_an_active_account_gets_a_session(db: Session) -> None:
    """§3.1: "Samo `ACTIVE` može kreirati ili obnoviti aplikacionu sesiju.\""""
    account, identity = _signed_in(db, subject="sub-inactive-issue")
    account.status = UserAccountStatus.SUSPENDED
    db.commit()
    with pytest.raises(ValueError):
        sessions.issue_session(db, account=account, identity=identity)


# ---------------------------------------------------------------------------
# §6 AUTH-03 — validation
# ---------------------------------------------------------------------------


def test_a_valid_credential_resolves(db: Session) -> None:
    account, identity = _signed_in(db, subject="sub-valid")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    validated = sessions.validate_session(db, credential)
    assert validated is not None
    assert validated[1].id == account.id


def test_use_slides_the_idle_deadline(db: Session) -> None:
    account, identity = _signed_in(db, subject="sub-slide")
    start = clock.now()
    session, credential = sessions.issue_session(
        db, account=account, identity=identity, now=start
    )
    db.commit()
    original = session.idle_expires_at

    later = start + dt.timedelta(minutes=10)
    sessions.validate_session(db, credential, now=later)
    db.commit()
    assert session.idle_expires_at > original
    assert session.last_seen_at == later


def test_sliding_never_pushes_past_the_absolute_deadline(db: Session) -> None:
    """Otherwise a client that polls often enough never logs out, and the twelve
    hours become a suggestion."""
    account, identity = _signed_in(db, subject="sub-slide-clamp")
    start = clock.now()
    session, credential = sessions.issue_session(
        db, account=account, identity=identity, absolute_hours=1, now=start
    )
    db.commit()

    # Used at 20 minutes, the idle deadline moves to 50 — still inside the
    # one-hour absolute. Used again at 45, it would move to 75, and is clamped.
    sessions.validate_session(db, credential, now=start + dt.timedelta(minutes=20))
    assert session.idle_expires_at == start + dt.timedelta(minutes=50)

    sessions.validate_session(db, credential, now=start + dt.timedelta(minutes=45))
    db.commit()
    assert session.idle_expires_at == session.absolute_expires_at


@pytest.mark.parametrize("minutes, ok", [(29, True), (31, False)])
def test_idle_expiry_is_enforced(db: Session, minutes: int, ok: bool) -> None:
    account, identity = _signed_in(db, subject=f"sub-idle-{minutes}")
    start = clock.now()
    _, credential = sessions.issue_session(
        db, account=account, identity=identity, now=start
    )
    db.commit()

    later = start + dt.timedelta(minutes=minutes)
    assert (sessions.validate_session(db, credential, now=later) is not None) is ok


def test_absolute_expiry_is_enforced_however_active_the_session(db: Session) -> None:
    """M01-QA-025: the local session keeps its own documented lifetime. Constant
    use extends the idle window and nothing else."""
    account, identity = _signed_in(db, subject="sub-absolute")
    start = clock.now()
    _, credential = sessions.issue_session(
        db, account=account, identity=identity, now=start
    )
    db.commit()

    # Used every ten minutes for thirteen hours.
    moment = start
    for _ in range(78):
        moment += dt.timedelta(minutes=10)
        if sessions.validate_session(db, credential, now=moment) is None:
            break
    db.commit()
    assert moment <= start + dt.timedelta(hours=12, minutes=10)
    assert sessions.validate_session(db, credential, now=moment) is None


def test_an_unknown_credential_resolves_to_nothing(db: Session) -> None:
    assert sessions.validate_session(db, "not-a-credential") is None


def test_a_suspended_account_kills_its_live_sessions(db: Session) -> None:
    """§3.1 again, from the read side. The session row is untouched — status is
    read fresh on every request, so the refusal needs no write to have
    happened."""
    account, identity = _signed_in(db, subject="sub-suspend-read")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    account.status = UserAccountStatus.SUSPENDED
    db.commit()
    assert sessions.validate_session(db, credential) is None


def test_a_disabled_account_kills_its_live_sessions(db: Session) -> None:
    """M01-QA-011."""
    account, identity = _signed_in(db, subject="sub-disable-read")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    account.status = UserAccountStatus.DISABLED
    account.disabled_at = clock.now()
    account.disabled_reason_code = AccountDisableReason.SECURITY_INCIDENT
    db.commit()
    assert sessions.validate_session(db, credential) is None


# ---------------------------------------------------------------------------
# §4.7 — the authorization version
# ---------------------------------------------------------------------------


def test_a_version_bump_invalidates_without_touching_the_session(db: Session) -> None:
    """§4.7, and the reason validation compares versions instead of trusting a
    flag: the refusal does not depend on any row having been rewritten, so
    there is no window between the commit and the bookkeeping (M01-QA-021)."""
    account, identity = _signed_in(db, subject="sub-bump")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    account.authorization_version += 1
    db.commit()
    assert sessions.validate_session(db, credential) is None


def test_a_version_that_moved_at_all_is_refused(db: Session) -> None:
    """Strict equality, not "at least". A version that somehow went backwards is
    a broken security clock, and the safe reading of a broken clock is no."""
    account, identity = _signed_in(db, subject="sub-bump-back")
    session, credential = sessions.issue_session(db, account=account, identity=identity)
    session.authorization_version_at_issue = account.authorization_version + 5
    db.commit()
    assert sessions.validate_session(db, credential) is None


# ---------------------------------------------------------------------------
# §6 AUTH-04 — revoke this session
# ---------------------------------------------------------------------------


def test_revoking_one_session_leaves_the_others(db: Session) -> None:
    """M01-QA-008: logging out of one browser is not logging out of all of
    them. That distinction is the reason `LogoutAll` is a separate command with
    its own proof requirements."""
    account, identity = _signed_in(db, subject="sub-one-of-two")
    laptop, laptop_cred = sessions.issue_session(db, account=account, identity=identity)
    _, phone_cred = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    sessions.revoke_session(db, laptop, reason=SessionRevokeReason.LOGOUT)
    db.commit()

    assert sessions.validate_session(db, laptop_cred) is None
    assert sessions.validate_session(db, phone_cred) is not None


def test_revocation_keeps_the_first_reason(db: Session) -> None:
    """The first revocation is the one that happened; overwriting it would lose
    why the session actually ended."""
    account, identity = _signed_in(db, subject="sub-twice")
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    assert sessions.revoke_session(db, session, reason=SessionRevokeReason.LOGOUT)
    assert not sessions.revoke_session(
        db, session, reason=SessionRevokeReason.SECURITY_EVENT
    )
    assert session.revoke_reason_code is SessionRevokeReason.LOGOUT


def test_a_revocation_time_needs_a_reason(db: Session) -> None:
    """§3.2, enforced by the database. A revoked session with no reason is a
    security event nobody can explain later."""
    account, identity = _signed_in(db, subject="sub-noreason")
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    session.revoked_at = clock.now()
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_revocation_writes_a_security_event(db: Session) -> None:
    """§13. The reason code is recorded; nothing else about the session is."""
    account, identity = _signed_in(db, subject="sub-event")
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    sessions.revoke_session(db, session, reason=SessionRevokeReason.LOGOUT)
    db.commit()

    events = db.execute(
        select(AuthenticationEvent).where(
            AuthenticationEvent.user_account_id == account.id,
            AuthenticationEvent.event_type == "auth.session_revoked",
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].reason_code == "LOGOUT"


# ---------------------------------------------------------------------------
# §6 AUTH-08 — revoke everything
# ---------------------------------------------------------------------------


def test_revoke_account_sessions_bumps_and_ends_everything(db: Session) -> None:
    """M01-QA-009."""
    account, identity = _signed_in(db, subject="sub-all")
    _, one = sessions.issue_session(db, account=account, identity=identity)
    _, two = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    before = account.authorization_version

    revoked = sessions.revoke_account_sessions(
        db, account, reason=SessionRevokeReason.LOGOUT_ALL, correlation_id="corr-1"
    )
    db.commit()

    assert revoked == 2
    assert account.authorization_version == before + 1
    assert sessions.validate_session(db, one) is None
    assert sessions.validate_session(db, two) is None


def test_a_kept_session_is_restamped_not_merely_spared(db: Session) -> None:
    """§6 allows keeping the session that performed the action. A kept session
    still carrying the old version would fail its very next request, which would
    make "keep" a lie."""
    account, identity = _signed_in(db, subject="sub-keep")
    keeper, keeper_cred = sessions.issue_session(db, account=account, identity=identity)
    _, other_cred = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    sessions.revoke_account_sessions(
        db, account, reason=SessionRevokeReason.LOGOUT_ALL, keep_session_id=keeper.id
    )
    db.commit()

    assert sessions.validate_session(db, keeper_cred) is not None
    assert sessions.validate_session(db, other_cred) is None


def test_revoke_all_emits_one_platform_event(db: Session) -> None:
    """M01-QA-028 and §13: one PLATFORM event with `school_id = NULL`, opaque
    ids only, and a dedupe key. M01 does not read memberships to fan it out —
    that coupling is exactly what §13 forbids, and the platform dispatcher owns
    the fan-out."""
    account, identity = _signed_in(db, subject="sub-outbox")
    sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    sessions.revoke_account_sessions(
        db, account, reason=SessionRevokeReason.ACCESS_CHANGED, correlation_id="corr-2"
    )
    db.commit()

    messages = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.event_type == AUTHORIZATION_INVALIDATED_EVENT
        )
    ).scalars().all()
    assert len(messages) == 1
    payload = messages[0].payload
    assert messages[0].school_id is None
    assert payload["user_account_id"] == account.id
    assert payload["authorization_version"] == account.authorization_version
    assert payload["dedupe_key"] == f"{account.id}:{account.authorization_version}"
    # §13: no raw email, IP, token, cookie or provider payload.
    assert set(payload) == {
        "user_account_id",
        "authorization_version",
        "reason_code",
        "correlation_id",
        "dedupe_key",
    }


def test_the_outbox_event_is_not_the_guard(db: Session) -> None:
    """§13: "Outbox je propagation/recovery mehanizam, ne dokaz da je budući
    request bezbedno odbijen."

    Proven by deleting the event and checking the refusal stands: nothing on the
    authorization path ever read it.
    """
    account, identity = _signed_in(db, subject="sub-nooutbox")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    sessions.revoke_account_sessions(db, account, reason=SessionRevokeReason.LOGOUT_ALL)
    db.commit()
    for message in db.execute(select(OutboxMessage)).scalars().all():
        db.delete(message)
    db.commit()

    assert sessions.validate_session(db, credential) is None


# ---------------------------------------------------------------------------
# The request path
# ---------------------------------------------------------------------------


def test_the_request_path_runs_validate_session(db: Session) -> None:
    """§6 AUTH-03 runs before every protected command, not at login only."""
    account, identity = _signed_in(db, subject="sub-request")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    principal = resolve_principal(_request(credential), db, get_settings())
    assert principal.person_id == account.person_id
    assert principal.user_account_id == account.id

    sessions.revoke_account_sessions(db, account, reason=SessionRevokeReason.LOGOUT_ALL)
    db.commit()
    with pytest.raises(UnauthorizedError):
        resolve_principal(_request(credential), db, get_settings())


def test_live_sessions_excludes_expired_and_revoked(db: Session) -> None:
    """What the security UI shows (§14 `UI-AUTH-04`)."""
    account, identity = _signed_in(db, subject="sub-live")
    start = clock.now()
    revoked, _ = sessions.issue_session(
        db, account=account, identity=identity, now=start
    )
    sessions.issue_session(
        db, account=account, identity=identity, absolute_hours=1, now=start
    )
    sessions.issue_session(db, account=account, identity=identity, now=start)
    db.commit()

    sessions.revoke_session(db, revoked, reason=SessionRevokeReason.LOGOUT)
    db.commit()

    later = start + dt.timedelta(hours=2)
    # Only the third survives: one revoked, one past its absolute deadline, and
    # the survivor is past its *idle* deadline too — so nothing is live.
    assert sessions.live_sessions(db, account.id, now=later) == []
    assert len(sessions.live_sessions(db, account.id, now=start)) == 2


def test_expire_marks_without_guarding(db: Session) -> None:
    """Bookkeeping, not a check: `is_live` compares timestamps, so the session
    was already dead before this ran. §5 keeps EXPIRED distinct from REVOKED so
    a list of revocations stays a list of decisions."""
    account, identity = _signed_in(db, subject="sub-expire")
    start = clock.now()
    session, credential = sessions.issue_session(
        db, account=account, identity=identity, absolute_hours=1, now=start
    )
    db.commit()

    later = start + dt.timedelta(hours=2)
    assert sessions.validate_session(db, credential, now=later) is None

    sessions.expire_session(db, session, now=later)
    db.commit()
    assert session.revoke_reason_code is SessionRevokeReason.EXPIRED


def test_identity_cannot_be_deleted_under_a_session(db: Session) -> None:
    """RESTRICT, not CASCADE: §6 AUTH-07 unlinks an identity and revokes the
    sessions it vouched for. Deleting the row instead would leave sessions whose
    provenance nobody can reconstruct."""
    account, identity = _signed_in(db, subject="sub-fkident")
    sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    with pytest.raises(IntegrityError):
        db.delete(find_identity(db, GOOGLE_ISSUER, "sub-fkident"))
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# Over HTTP, end to end
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str) -> None:
    resp = client.post(
        "/auth/password/register",
        json={
            "email": email,
            "password": "dovoljnodugo1",
            "given_name": "H",
            "family_name": "T",
        },
    )
    assert resp.status_code == 200


def test_logout_over_http_revokes_on_the_server(client: TestClient, db: Session) -> None:
    """M01-QA-008. The part that matters is the *server* refusal: clearing the
    cookie only tidies up this browser, and §6 requires that a credential
    presented after logout fail at the server."""
    _register(client, "http@example.invalid")
    credential = _credential_from(client)

    assert sessions.validate_session(db, credential) is not None
    assert client.post("/auth/logout").status_code == 204

    db.expire_all()
    assert sessions.validate_session(db, credential) is None
    session = db.execute(
        select(AuthSession).where(
            AuthSession.credential_hash == sessions.hash_credential(credential)
        )
    ).scalar_one()
    assert session.revoke_reason_code is SessionRevokeReason.LOGOUT


def test_logging_in_twice_makes_two_sessions(client: TestClient, db: Session) -> None:
    """Two browsers, two rows — which is what makes "log out of this one" and
    "log out of all of them" different commands rather than the same one."""
    _register(client, "dva@example.invalid")
    first = _credential_from(client)
    resp = client.post(
        "/auth/password/login",
        json={"email": "dva@example.invalid", "password": "dovoljnodugo1"},
    )
    assert resp.status_code == 200
    second = _credential_from(client)

    assert first != second
    assert db.execute(select(func.count()).select_from(AuthSession)).scalar_one() == 2


def test_logout_without_a_session_is_a_safe_no_op(client: TestClient) -> None:
    """§6: with no credential the client cleans up locally and the endpoint
    returns a safe empty success — without claiming a revocation it did not
    perform."""
    assert client.post("/auth/logout").status_code == 204


def _credential_from(client: TestClient) -> str:
    """Read the credential back out of the signed cookie the way the server
    would, so the test asserts against what the browser is actually holding."""
    import base64
    import json

    from itsdangerous import TimestampSigner

    raw = client.cookies["session"]
    signer = TimestampSigner(get_settings().session_secret)
    payload = signer.unsign(raw, max_age=None)
    data = json.loads(base64.urlsafe_b64decode(payload))
    return str(data[SESSION_CREDENTIAL_KEY])
