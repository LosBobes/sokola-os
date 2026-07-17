"""Authentication endpoints: Google OIDC login + session logout.

The session is a signed cookie (Starlette SessionMiddleware) holding only the
resolved ``person_id`` and a CSRF synchronizer token. Google is used to prove
identity; SOKOLA issues the session. The acting organization/role is still
chosen separately and re-derived server-side on every request.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from starlette.status import HTTP_204_NO_CONTENT

from app.common.errors import NotFoundError, UnauthorizedError
from app.db import SessionLocal
from app.security.csrf import CSRF_COOKIE
from app.security.deps import SettingsDep
from app.security.oidc import get_oauth, jit_provision

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


class AuthConfig(BaseModel):
    google_enabled: bool
    dev_auth_enabled: bool


@router.get("/auth/config", response_model=AuthConfig, operation_id="authConfig")
def auth_config(settings: SettingsDep) -> AuthConfig:
    """Tell the frontend which sign-in methods are available."""
    return AuthConfig(
        google_enabled=settings.oidc_enabled,
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

    request.session["person_id"] = person.id
    # Issue a CSRF synchronizer token: stored in the signed session and mirrored
    # in a JS-readable cookie the SPA echoes back via X-CSRF-Token.
    csrf = secrets.token_urlsafe(32)
    request.session["csrf"] = csrf

    resp = RedirectResponse(url=settings.web_post_login_url)
    resp.set_cookie(
        CSRF_COOKIE,
        csrf,
        samesite="lax",
        httponly=False,
        secure=settings.is_production_like,
        path="/",
    )
    return resp


@router.post("/auth/logout", status_code=HTTP_204_NO_CONTENT, operation_id="logout")
def logout(request: Request) -> Response:
    request.session.clear()
    resp = Response(status_code=HTTP_204_NO_CONTENT)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp
