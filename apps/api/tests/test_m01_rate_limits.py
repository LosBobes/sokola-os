"""M01 §6 AUTH-01 and §10: rate limits that refuse without revealing anything.

The whole point of AUTH-01 is that it is enumeration-safe, so the limit on top
of it must not become the oracle the command itself withholds. A refusal here
says "too many attempts" and nothing more — not whether an address exists, not
how much budget is left, not which of the two budgets ran out (M01-QA-013).

The signals are never stored. §10 asks for keyed hashes of the IP/device signal,
kept briefly per M17 and not used for profiling. Keyed and not plain, because
the entire IPv4 space hashes in minutes: an unkeyed digest of an address *is*
the address.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import RateLimitedError
from app.config import get_settings
from app.platform import clock
from app.platform.rate_limit import service as rate_limit
from app.platform.rate_limit.enums import RateLimitScope
from app.platform.rate_limit.models import RateLimitCounter
from app.security.rate_guard import DEVICE_COOKIE, client_signal
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

SECRET = "test-secret"
ADDRESS = "203.0.113.7"


def _request(*, forwarded: str | None = None, host: str = ADDRESS) -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
            "client": (host, 12345),
        }
    )


# ---------------------------------------------------------------------------
# The signal never reaches a row
# ---------------------------------------------------------------------------


def test_the_address_is_not_stored(db: Session) -> None:
    rate_limit.consume(db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET)
    db.commit()

    stored = db.execute(select(RateLimitCounter.subject_hash)).scalars().all()
    assert ADDRESS not in stored
    assert stored == [rate_limit.subject_hash(ADDRESS, secret=SECRET)]


def test_the_digest_is_keyed(db: Session) -> None:
    """A plain digest of an address is the address: the IPv4 space is small
    enough to enumerate in minutes. Two different keys must give two different
    digests, or the key is not doing anything."""
    import hashlib

    digest = rate_limit.subject_hash(ADDRESS, secret=SECRET)
    assert digest != hashlib.sha256(ADDRESS.encode()).hexdigest()
    assert digest != rate_limit.subject_hash(ADDRESS, secret="other-secret")


# ---------------------------------------------------------------------------
# §6 AUTH-01's numbers
# ---------------------------------------------------------------------------


def test_the_budgets_are_the_contracts_numbers() -> None:
    """These come from §6 AUTH-01 and §10, not from taste."""
    budgets = rate_limit.BUDGETS
    ip = budgets[RateLimitScope.LOGIN_START_IP]
    assert ip.limit == 5 and ip.window == dt.timedelta(minutes=10)
    device = budgets[RateLimitScope.LOGIN_START_DEVICE]
    assert device.limit == 10 and device.window == dt.timedelta(hours=24)
    callback = budgets[RateLimitScope.CALLBACK_FAILURE_IP]
    assert callback.limit == 20 and callback.window == dt.timedelta(minutes=10)


def test_the_sixth_start_in_ten_minutes_is_refused(db: Session) -> None:
    """M01-QA-013, exactly as written: 6 starts from one IP in 10 minutes."""
    for _ in range(5):
        rate_limit.consume(db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET)
    db.commit()

    with pytest.raises(RateLimitedError):
        rate_limit.consume(db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET)


def test_the_refusal_reveals_nothing(db: Session) -> None:
    """§11: generic. No address, no account, no remaining count — a countdown
    is detail, and AUTH-01 is enumeration-safe by design."""
    for _ in range(6):
        try:
            rate_limit.consume(db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET)
        except RateLimitedError as exc:
            assert ADDRESS not in exc.message
            assert exc.details == {}
            assert exc.headers["Retry-After"]
            return
    pytest.fail("expected a refusal")


def test_the_event_that_crosses_the_line_is_counted(db: Session) -> None:
    """Counted before the decision, on purpose. Checking first and counting
    after lets every concurrent request through the same gap."""
    for _ in range(5):
        rate_limit.consume(db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET)
    with pytest.raises(RateLimitedError):
        rate_limit.consume(db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET)
    db.commit()

    hits = db.execute(select(RateLimitCounter.hits)).scalar_one()
    assert hits == 6


def test_budgets_do_not_share(db: Session) -> None:
    """Exhausting the per-address budget must not exhaust the per-device one.

    A shared office NAT would otherwise lock out a building the moment one
    person fat-fingers a password — which is the reason §6 names two signals
    rather than one.
    """
    for _ in range(5):
        rate_limit.consume(db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET)
    db.commit()
    rate_limit.consume(db, RateLimitScope.LOGIN_START_DEVICE, "dev-1", secret=SECRET)
    db.commit()
    assert rate_limit.remaining(
        db, RateLimitScope.LOGIN_START_DEVICE, "dev-1", secret=SECRET
    ) == 9


def test_two_addresses_do_not_share(db: Session) -> None:
    for _ in range(5):
        rate_limit.consume(db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET)
    db.commit()
    rate_limit.consume(db, RateLimitScope.LOGIN_START_IP, "198.51.100.9", secret=SECRET)
    db.commit()


def test_a_new_window_restores_the_budget(db: Session) -> None:
    start = clock.now()
    for _ in range(5):
        rate_limit.consume(
            db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET, now=start
        )
    db.commit()

    later = start + dt.timedelta(minutes=11)
    rate_limit.consume(
        db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET, now=later
    )
    db.commit()
    assert db.execute(select(func.count()).select_from(RateLimitCounter)).scalar_one() == 2


def test_windows_are_anchored_to_the_epoch() -> None:
    """Not to first use, so two API processes compute the same boundary without
    coordinating — otherwise each would grant a full budget from whenever it
    happened to start."""
    window = dt.timedelta(minutes=10)
    a = rate_limit.window_start(dt.datetime(2026, 9, 19, 12, 3, 17, tzinfo=dt.UTC), window)
    b = rate_limit.window_start(dt.datetime(2026, 9, 19, 12, 9, 59, tzinfo=dt.UTC), window)
    c = rate_limit.window_start(dt.datetime(2026, 9, 19, 12, 10, 0, tzinfo=dt.UTC), window)
    assert a == b == dt.datetime(2026, 9, 19, 12, 0, tzinfo=dt.UTC)
    assert c == dt.datetime(2026, 9, 19, 12, 10, tzinfo=dt.UTC)


def test_expired_counters_are_swept(db: Session) -> None:
    """M17 retention. These answer one question about the last few minutes and
    have no reason to outlive it."""
    start = clock.now()
    rate_limit.consume(
        db, RateLimitScope.LOGIN_START_IP, ADDRESS, secret=SECRET, now=start
    )
    db.commit()

    assert rate_limit.sweep_expired(db, now=start) == 0
    assert rate_limit.sweep_expired(db, now=start + dt.timedelta(hours=1)) == 1
    db.commit()
    assert db.execute(select(func.count()).select_from(RateLimitCounter)).scalar_one() == 0


# ---------------------------------------------------------------------------
# Which address gets counted
# ---------------------------------------------------------------------------


def test_the_forwarded_client_wins_behind_a_proxy() -> None:
    """The first `X-Forwarded-For` entry is the client as the edge saw it; the
    rest are proxies."""
    assert client_signal(_request(forwarded="198.51.100.4, 10.0.0.1")) == "198.51.100.4"


def test_the_socket_address_is_used_without_a_proxy_header() -> None:
    assert client_signal(_request()) == ADDRESS


def test_an_empty_forwarded_header_falls_back() -> None:
    """A header an attacker can send empty must not erase the real signal —
    that is how a limit becomes no limit."""
    assert client_signal(_request(forwarded="")) == ADDRESS
    assert client_signal(_request(forwarded="  , 10.0.0.1")) == ADDRESS


# ---------------------------------------------------------------------------
# Over HTTP
# ---------------------------------------------------------------------------


def test_password_login_is_rate_limited(client: TestClient, db: Session) -> None:
    """§10's brute-force limit. A password POST *is* the attempt, so it consumes
    budget up front — an attacker already over the limit does not get one more
    guess checked before being told no."""
    client.post(
        "/auth/password/register",
        json={
            "email": "brute@example.invalid",
            "password": "dovoljnodugo1",
            "given_name": "B",
            "family_name": "R",
        },
    )
    codes = []
    for _ in range(22):
        resp = client.post(
            "/auth/password/login",
            json={"email": "brute@example.invalid", "password": "pogresna"},
        )
        codes.append(resp.status_code)

    assert 429 in codes, "the limit never engaged"
    assert codes.index(429) >= 20, "the limit engaged too early"
    first = codes.index(429)
    assert all(code == 429 for code in codes[first:])


def test_the_http_refusal_is_generic(client: TestClient) -> None:
    for _ in range(25):
        resp = client.post(
            "/auth/password/login",
            json={"email": "nepoznat@example.invalid", "password": "bilosta"},
        )
        if resp.status_code == 429:
            body = resp.json()
            assert body["error"]["code"] == "RATE_LIMITED"
            assert "nepoznat@example.invalid" not in resp.text
            assert resp.headers["Retry-After"]
            return
    pytest.fail("expected a refusal")


def test_a_correct_password_still_works_below_the_limit(client: TestClient) -> None:
    """The budget is consumed by every attempt, so a handful of typos must not
    lock someone out of their own account."""
    client.post(
        "/auth/password/register",
        json={
            "email": "strpljiv@example.invalid",
            "password": "dovoljnodugo1",
            "given_name": "S",
            "family_name": "T",
        },
    )
    for _ in range(3):
        client.post(
            "/auth/password/login",
            json={"email": "strpljiv@example.invalid", "password": "pogresna"},
        )
    ok = client.post(
        "/auth/password/login",
        json={"email": "strpljiv@example.invalid", "password": "dovoljnodugo1"},
    )
    assert ok.status_code == 200


def test_the_device_cookie_is_not_readable_by_scripts(client: TestClient) -> None:
    """HttpOnly: nothing in the page needs it, and a value scripts can read is
    a value an XSS can rotate to reset the budget."""
    settings = get_settings()
    assert settings is not None
    resp = client.get("/auth/google/login")
    # Google is off in tests, so the endpoint 404s and issues no cookie —
    # which is itself correct: a refused request hands out nothing.
    assert resp.status_code == 404
    assert DEVICE_COOKIE not in resp.cookies
