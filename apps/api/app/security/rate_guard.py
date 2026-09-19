"""M01 §6 AUTH-01 and §10, applied to the authentication endpoints.

Kept beside the other security adapters rather than in the router, because
deciding *what counts as one person trying repeatedly* is a security judgement
and not an HTTP detail.

Two signals, deliberately different in kind:

* the **client address**, which is cheap and always present, and is also shared
  by everyone behind one office NAT — so its budget is short and forgiving;
* a **device id**, a random value in a long-lived cookie. §6 AUTH-01 asks for a
  "browser/device signal" and this is the honest version of one: something we
  issued and can forget, rather than a fingerprint assembled from the browser's
  properties. §10 forbids using these for profiling, and a value with no
  meaning outside the counter cannot be used for it.

Neither signal is stored. Both are hashed with a key before they reach a row.
"""

from __future__ import annotations

import secrets

from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings
from app.platform.rate_limit import service as rate_limit
from app.platform.rate_limit.enums import RateLimitScope

#: Long-lived, HttpOnly, and meaningless on its own. It identifies a browser to
#: the rate counter and to nothing else — it is not a session, not a person and
#: not a login hint.
DEVICE_COOKIE = "sokola_device"
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 400


def client_signal(request: Request) -> str:
    """The address to count against.

    ``X-Forwarded-For``'s *first* entry is the client as the edge saw it; the
    rest are proxies. Trusting it at all assumes we sit behind a proxy that
    rewrites it, which this deployment does — read directly from the internet
    it would be attacker-chosen, and the limit would be no limit at all. That
    tradeoff is the reason this is one small function with its own name.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client is not None else "unknown"


def device_signal(request: Request) -> str | None:
    """This browser's id, if it already has one."""
    value = request.cookies.get(DEVICE_COOKIE)
    return value or None


def issue_device_cookie(response: Response, settings: Settings) -> str:
    """Give this browser an id so the per-device budget has something to count.

    HttpOnly: nothing in the page needs to read it, and a value scripts can
    read is a value an XSS can rotate to reset the budget.
    """
    device_id = secrets.token_urlsafe(16)
    response.set_cookie(
        DEVICE_COOKIE,
        device_id,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.is_production_like,
        path="/",
    )
    return device_id


def guard_login_start(db: Session, request: Request, settings: Settings) -> None:
    """§6 AUTH-01: 5 per address per 10 minutes, 10 per device per 24 hours.

    Both budgets are consumed, and either can refuse. A shared address should
    not lock out a building, and a single device should not get a fresh
    allowance by moving to a different network — the two limits cover each
    other's blind spot, which is why the contract names both.

    The refusal is `RATE_LIMITED` and says nothing else (M01-QA-013): AUTH-01 is
    enumeration-safe, and a limit that confirmed an address existed would undo
    that at the last step.
    """
    rate_limit.consume(
        db,
        RateLimitScope.LOGIN_START_IP,
        client_signal(request),
        secret=settings.session_secret,
    )
    device = device_signal(request)
    if device is not None:
        rate_limit.consume(
            db,
            RateLimitScope.LOGIN_START_DEVICE,
            device,
            secret=settings.session_secret,
        )


def guard_failure(
    db: Session, request: Request, settings: Settings, scope: RateLimitScope
) -> None:
    """Count a failed attempt (§10: 20 per address per 10 minutes).

    Counted on failure only. Counting successes here would mean a busy, honest
    user in a shared office eventually locks themselves out by signing in
    normally.
    """
    rate_limit.consume(db, scope, client_signal(request), secret=settings.session_secret)
