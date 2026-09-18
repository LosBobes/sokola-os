"""Authentication endpoints: email+password login, Google OIDC login, logout.

The session is a signed cookie (Starlette SessionMiddleware) holding only the
resolved ``person_id`` and a CSRF synchronizer token. A password check or Google
proves identity; SOKOLA issues the session. The acting school/role is still
chosen separately and re-derived server-side on every request.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from starlette.status import HTTP_204_NO_CONTENT

from app.common.errors import NotFoundError, UnauthorizedError
from app.config import Settings
from app.db import SessionLocal
from app.domains.identity.models import Person
from app.security.csrf import CSRF_COOKIE
from app.security.deps import SettingsDep
from app.security.oidc import get_oauth, jit_provision
from app.security.password import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.security.password_auth import authenticate_with_password, register_with_password

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


class AuthConfig(BaseModel):
    google_enabled: bool
    password_enabled: bool
    dev_auth_enabled: bool


@router.get("/auth/config", response_model=AuthConfig, operation_id="authConfig")
def auth_config(settings: SettingsDep) -> AuthConfig:
    """Tell the frontend which sign-in methods are available."""
    return AuthConfig(
        google_enabled=settings.oidc_enabled,
        password_enabled=settings.password_auth_enabled,
        dev_auth_enabled=settings.allow_insecure_dev_auth,
    )


@router.get("/auth/google/login", operation_id="googleLogin")
async def google_login(request: Request, settings: SettingsDep) -> RedirectResponse:
    if not settings.oidc_enabled:
        raise NotFoundError("Google prijava nije konfigurisana.")
    oauth = get_oauth()
    try:
        redirect = await oauth.google.authorize_redirect(request, settings.oidc_redirect_url)
    except Exception:
        # Provider discovery/redirect unavailable → don't 500, send the user back
        # to the sign-in page with a soft failure notice.
        logger.exception("Google login redirect failed")
        return RedirectResponse(url=f"{settings.web_post_login_url}?login=failed")
    return cast(RedirectResponse, redirect)


_ResponseT = TypeVar("_ResponseT", RedirectResponse, JSONResponse)


def _establish_session(
    request: Request, settings: Settings, person: Person, resp: _ResponseT
) -> _ResponseT:
    """Sign the session cookie (via SessionMiddleware) and issue the CSRF
    synchronizer token onto ``resp``. Shared by every login method, the Google
    redirect flow and the password XHR flow alike."""
    request.session["person_id"] = person.id
    # Issue a CSRF synchronizer token: stored in the signed session and mirrored
    # in a JS-readable cookie the SPA echoes back via X-CSRF-Token.
    csrf = secrets.token_urlsafe(32)
    request.session["csrf"] = csrf

    resp.set_cookie(
        CSRF_COOKIE,
        csrf,
        samesite="lax",
        httponly=False,
        secure=settings.is_production_like,
        path="/",
    )
    return resp


def _issue_session(request: Request, settings: Settings, person: Person) -> RedirectResponse:
    """Redirect-flow session issuance: land the browser in the SPA already
    authenticated (the Google callback)."""
    resp = RedirectResponse(url=settings.web_post_login_url)
    return _establish_session(request, settings, person, resp)


@router.get("/auth/google/callback", operation_id="googleCallback")
async def google_callback(request: Request, settings: SettingsDep) -> RedirectResponse:
    if not settings.oidc_enabled:
        raise NotFoundError("Google prijava nije konfigurisana.")
    oauth = get_oauth()
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        # Token exchange failed (provider outage, expired state, user denied) →
        # soft failure rather than a 500.
        logger.exception("Google token exchange failed")
        return RedirectResponse(url=f"{settings.web_post_login_url}?login=failed")

    claims: dict[str, Any] | None = token.get("userinfo")
    if not claims or "sub" not in claims:
        raise UnauthorizedError("Prijava nije uspela.")

    with SessionLocal() as db:
        person = jit_provision(db, dict(claims))

    return _issue_session(request, settings, person)


class PasswordLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class PasswordRegisterRequest(PasswordLoginRequest):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    given_name: str = Field(min_length=1, max_length=120)
    family_name: str = Field(min_length=1, max_length=120)


class PasswordAuthResponse(BaseModel):
    person_id: str
    display_name: str


def _password_session_response(
    request: Request, settings: Settings, person: Person
) -> JSONResponse:
    """Establish the session cookie on a JSON body the SPA reads directly (no
    redirect, password login is an XHR, not a browser navigation)."""
    resp = JSONResponse(
        PasswordAuthResponse(person_id=person.id, display_name=person.display_name).model_dump()
    )
    return _establish_session(request, settings, person, resp)


@router.post(
    "/auth/password/register",
    response_model=PasswordAuthResponse,
    operation_id="registerWithPassword",
)
def password_register(
    body: PasswordRegisterRequest, request: Request, settings: SettingsDep
) -> JSONResponse:
    if not settings.password_auth_enabled:
        raise NotFoundError("Prijava lozinkom nije omogućena.")
    with SessionLocal() as db:
        person = register_with_password(
            db, body.email, body.password, body.given_name, body.family_name
        )
    return _password_session_response(request, settings, person)


@router.post(
    "/auth/password/login",
    response_model=PasswordAuthResponse,
    operation_id="loginWithPassword",
)
def password_login(
    body: PasswordLoginRequest, request: Request, settings: SettingsDep
) -> JSONResponse:
    if not settings.password_auth_enabled:
        raise NotFoundError("Prijava lozinkom nije omogućena.")
    with SessionLocal() as db:
        person = authenticate_with_password(db, body.email, body.password)
    return _password_session_response(request, settings, person)


@router.post("/auth/logout", status_code=HTTP_204_NO_CONTENT, operation_id="logout")
def logout(request: Request) -> Response:
    request.session.clear()
    resp = Response(status_code=HTTP_204_NO_CONTENT)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp
