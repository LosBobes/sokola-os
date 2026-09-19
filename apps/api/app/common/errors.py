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


class IdentityAlreadyLinkedError(ConflictError):
    """M01 §11: this provider subject already belongs to an account.

    §11 adds "samo ovlašćenom potvrđenom akteru; ne otkriva drugi nalog" — the
    caller learns the subject is taken and nothing about who has it, because
    "which account owns this Google address" is exactly the question an attacker
    would like answered.
    """

    code = "IDENTITY_ALREADY_LINKED"


class LastIdentityProtectedError(ConflictError):
    """M01 §11: the account's last way to sign in cannot be removed.

    §2 requires every ACTIVE or SUSPENDED account to keep at least one linked
    identity. Without this an account-security screen could lock someone out of
    their own account in one click, and nothing in M01 could let them back in.
    """

    code = "LAST_IDENTITY_PROTECTED"


class ReauthenticationRequiredError(ForbiddenError):
    """M01 §6 AUTH-06/07: the action needs a fresh provider authentication.

    Distinct from `UNAUTHENTICATED`: the session is perfectly valid, it is just
    not *recent* enough to authorize changing how the account signs in. Telling
    the two apart is what lets a client re-authenticate instead of logging out.
    """

    code = "REAUTHENTICATION_REQUIRED"


class StaleVersionError(ConflictError):
    """M01 §11: `expected_version` no longer matches. Reload and retry."""

    code = "STALE_VERSION"


class InvalidAccountTransitionError(ConflictError):
    """M01 §11: the requested status change is not allowed from the current one.

    §5's table has no row out of `DISABLED` or `MERGED_RETIRED`, and this is
    what a caller who tries anyway gets — never a silent no-op.
    """

    code = "INVALID_ACCOUNT_TRANSITION"

class ValidationFailedError(AppError):
    """M07 §6 `M07_VALIDATION_FAILED`: a field, date or reason a handler
    rejected, as opposed to one the request schema could not parse.

    422 like FastAPI's own `RequestValidationError`, under a distinct code, so
    a client can tell "this shape is wrong" from "this shape is fine and the
    rule it breaks is a business one" — the second is actionable, the first is
    a bug in the caller.
    """

    status_code = 422
    code = "VALIDATION_FAILED"


class FamilyArchiveBlockedError(ConflictError):
    """M07 §3.13 / §6 `M07_FAMILY_ARCHIVE_BLOCKED`.

    A family may only be archived once nothing rests on it: no active
    membership, no open payer link, no outstanding M12 obligation. Refusing is
    the whole point — archiving anyway would leave a financial arrangement
    pointing at a grouping the school considers closed.
    """

    code = "FAMILY_ARCHIVE_BLOCKED"


class RelationshipExistsError(ConflictError):
    """M07 §6 `M07_RELATIONSHIP_EXISTS` / `M07_FAMILY_MEMBERSHIP_EXISTS`.

    The open natural key is taken. Distinct from a stale version: nothing the
    caller reloads will change it, because the conflict is with a row that is
    supposed to be there.
    """

    code = "RELATIONSHIP_EXISTS"


class InvalidRelationshipTransitionError(ConflictError):
    """M07 §6 `M07_RELATIONSHIP_INVALID_TRANSITION`.

    §5's tables make `ENDED`, `REJECTED`, `REVOKED` and `ARCHIVED` terminal;
    coming back is a new row with a new id. A caller who tries anyway gets
    this rather than a silent no-op, because a no-op here reads to the client
    as "done" when nothing happened.
    """

    code = "RELATIONSHIP_INVALID_TRANSITION"


class DependencyUnavailableError(AppError):
    """M07 §6 `M07_DEPENDENCY_UNAVAILABLE`, and §6 says fail-closed.

    Raised when an authoritative guard cannot be consulted — not when it
    answers no. The distinction matters: "the finance module says there are no
    open obligations" and "the finance module could not be reached" must not
    produce the same outcome, and the second one is 503 rather than a
    permissive guess.
    """

    status_code = 503
    code = "DEPENDENCY_UNAVAILABLE"



class TenantContextRequiredError(ConflictError):
    """M03 §13: a school must be chosen, or the previous choice was invalidated.

    409 rather than 403 because nothing is forbidden — the request simply has
    no school to act in yet. §13 adds "bez razloga/tuđih podataka": it does not
    say which school went away or why.
    """

    code = "TENANT_CONTEXT_REQUIRED"


class TenantContextStaleError(ConflictError):
    """M03 §13: the context's version snapshot no longer matches its authority.

    The client refreshes the chooser and picks again. Distinct from
    `TENANT_CONTEXT_NOT_AVAILABLE`, which means the choice itself is gone
    rather than merely old.
    """

    code = "TENANT_CONTEXT_STALE"


class TenantContextNotAvailableError(ForbiddenError):
    """M03 §13: a context that used to be allowed is not any more.

    §13: "redovni payload nije vraćen" — the refusal carries no tenant data and
    no reason, because "your membership was revoked" and "the school was
    deactivated" are both things the person may learn elsewhere and neither is
    safe to infer from an error.
    """

    code = "TENANT_CONTEXT_NOT_AVAILABLE"


class TenantSwitchConflictError(ConflictError):
    """M03 §13: two tabs switched at once; the winner's context stands.

    §14 requires exactly one to succeed. The loser is told rather than silently
    overwritten, because the alternative is a person acting in a school they
    can see they did not choose.
    """

    code = "TENANT_SWITCH_CONFLICT"


class TenantResourceNotFoundError(NotFoundError):
    """M03 §13: the resource is absent from the active tenant, or belongs to
    another one — and §8 requires those to be indistinguishable from outside,
    since telling them apart is how a guessed id confirms a school's contents."""

    code = "TENANT_RESOURCE_NOT_FOUND_SAFE"


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
