"""Uniform error envelope and exception handlers.

Every error the client sees has the shape::

    {"error": {"code": "CONFLICT", "message": "...", "details": {...}}}

We never leak stack traces, provider names, SQL, or internal DTO terms. Codes are
stable, screaming-snake strings the web adapter maps to canonical UI states
(401/403 -> permission, 409 -> conflict/review, 5xx -> manual recovery).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"
    #: Response headers this error carries. Some errors are only actionable with
    #: one — M01 §11 pairs `IDEMPOTENCY_IN_PROGRESS` and `RATE_LIMITED` with
    #: `Retry-After`, and without it the client is told to wait but not how long.
    headers: dict[str, str] = {}

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class VersionConflictError(ConflictError):
    """Optimistic-concurrency failure: caller must reload and reapply."""

    code = "VERSION_CONFLICT"


class IdempotencyConflictError(ConflictError):
    """Same idempotency key reused with different parameters."""

    code = "IDEMPOTENCY_CONFLICT"


class IdempotencyKeyReusedError(IdempotencyConflictError):
    """M01 §11: same key, different canonical payload.

    Distinct from the generic conflict above because M01's contract names this
    code, and a client that retries a *changed* payload under an old key has a
    bug the generic message would hide.
    """

    code = "IDEMPOTENCY_KEY_REUSED"


class IdempotencyInProgressError(ConflictError):
    """M01 §12: an identical request is still running and has no durable result.

    The client is told to come back in a second rather than being served a
    half-finished answer — and never by executing the side effect a second time.
    """

    code = "IDEMPOTENCY_IN_PROGRESS"
    headers = {"Retry-After": "1"}


class IdempotencyKeyInvalidError(BadRequestError):
    """M01 §12: a write with no valid UUID key, or an `Idempotency-Key` header
    that does not match the body's `request_id`.

    Refused before any business write, so a mismatched pair never produces a
    state change, a receipt, an audit success or an outbox message.
    """

    code = "IDEMPOTENCY_KEY_INVALID"


class ProviderNotAllowedError(BadRequestError):
    """M01 §11: the issuer is not in the active fail-closed registry.

    One message for every reason the registry refused. Distinguishing "unknown
    issuer" from "wrong audience" from "disabled provider" would tell an
    attacker which knob to turn.
    """

    code = "PROVIDER_NOT_ALLOWED"


class StaleVersionError(ConflictError):
    """M01 §11: `expected_version` no longer matches. Reload and retry."""

    code = "STALE_VERSION"


class InvalidAccountTransitionError(ConflictError):
    """M01 §11: the requested status change is not allowed from the current one.

    §5's table has no row out of `DISABLED` or `MERGED_RETIRED`, and this is
    what a caller who tries anyway gets — never a silent no-op.
    """

    code = "INVALID_ACCOUNT_TRANSITION"


class RateLimitedError(AppError):
    """M01 §11: generic "please wait", with no confirmation of what exists."""

    status_code = 429
    code = "RATE_LIMITED"
    headers = {"Retry-After": "60"}


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Surface field paths and rules, but nothing about internal types.
        details = {
            "fields": [
                {"loc": [str(p) for p in err["loc"]], "rule": err["type"]}
                for err in exc.errors()
            ]
        }
        return JSONResponse(
            status_code=422,
            content=_envelope("VALIDATION_ERROR", "Neispravni podaci u zahtevu.", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        message = exc.detail if isinstance(exc.detail, str) else "Zahtev nije uspeo."
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, message))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Never reveal internals. Details are logged server-side elsewhere.
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL_ERROR", "Došlo je do neočekivane greške."),
        )
