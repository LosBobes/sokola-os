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
