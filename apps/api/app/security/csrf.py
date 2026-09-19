"""CSRF protection for cookie-authenticated mutations.

The session cookie is ``SameSite=Lax``, which already stops cross-site
POST/PUT/PATCH/DELETE from carrying it. This adds defense-in-depth with a
synchronizer token: a random value is stored in the signed cookie at login and
mirrored in a JS-readable ``sokola_csrf`` cookie; the SPA echoes it in the
``X-CSRF-Token`` header, and unsafe cookie-authenticated requests must match.

Dev-header auth carries no cookie, so it is unaffected (the session credential
is absent). The ``/auth/`` login endpoints are exempt (GET flow + logout).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

#: Imported rather than repeated: if the cookie's session key ever changes,
#: a stale copy here would silently switch CSRF checking off.
from app.security.auth import SESSION_CREDENTIAL_KEY

CSRF_COOKIE = "sokola_csrf"
CSRF_HEADER = "x-csrf-token"
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def csrf_required(method: str, path: str) -> bool:
    return method.upper() in _UNSAFE and not path.startswith("/auth/")


def csrf_ok(session: dict[str, Any], header_value: str | None) -> bool:
    """A request is allowed when it isn't cookie-authenticated, or when its
    ``X-CSRF-Token`` matches the token stored in the cookie.

    "Cookie-authenticated" is decided by the presence of the session credential,
    not by any person or account id — M01 §3.2 keeps those out of the cookie
    entirely, and this check must not be the reason one comes back.
    """
    if not session.get(SESSION_CREDENTIAL_KEY):
        return True  # not a session-cookie request (e.g. dev header) → no CSRF
    expected = session.get("csrf")
    return bool(expected) and header_value == expected


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if csrf_required(request.method, request.url.path):
            session = request.scope.get("session") or {}
            if not csrf_ok(session, request.headers.get(CSRF_HEADER)):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "CSRF_FAILED",
                            "message": "Bezbednosna provera nije uspela. Osvežite stranicu.",
                        }
                    },
                )
        return await call_next(request)
