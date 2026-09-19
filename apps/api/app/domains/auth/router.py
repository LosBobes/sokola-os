"""Authentication endpoints: email+password login, Google OIDC login, logout.

A password check or Google proves identity; SOKOLA then issues a **server-side**
session (M01 §3.2) and puts only its opaque credential into the signed cookie,
alongside a CSRF synchronizer token. The cookie is transport; the `auth_session`
row is the session, which is what makes logout something the server does rather
than something the browser is asked to do.

The acting school/role is still chosen separately and re-derived server-side on
every request.
"""

from __future__ import annotations

import datetime as dt
import logging
import secrets
from contextlib import suppress
from typing import Annotated, Any, TypeVar, cast

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.status import HTTP_204_NO_CONTENT

from app.common.errors import (
    NotFoundError,
    ProviderNotAllowedError,
    RateLimitedError,
    UnauthorizedError,
)
from app.config import Settings
from app.db import SessionLocal
from app.domains.identity import accounts, auth_commands, auth_providers, sessions
from app.domains.identity.auth_enums import (
    GOOGLE_PROVIDER,
    AuthCommand,
    AuthEventOutcome,
    AuthEventType,
    SessionRevokeReason,
    UserAccountStatus,
)
from app.domains.identity.auth_models import (
    AuthenticationEvent,
    AuthIdentity,
    AuthSession,
    UserAccount,
)
from app.domains.identity.models import Person
from app.platform import clock
from app.platform.rate_limit.enums import RateLimitScope
from app.security import rate_guard
from app.security.auth import SESSION_CREDENTIAL_KEY
from app.security.csrf import CSRF_COOKIE
from app.security.deps import SettingsDep
from app.security.oidc import (
    assurance_of,
    auth_time_of,
    claims_for_registry,
    get_oauth,
    jit_provision,
)
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
    with SessionLocal() as db:
        rate_guard.guard_login_start(db, request, settings)
        db.commit()
    _record_login_started(GOOGLE_PROVIDER)
    try:
        redirect = await oauth.google.authorize_redirect(request, settings.oidc_redirect_url)
    except Exception:
        # Provider discovery/redirect unavailable → don't 500, send the user back
        # to the sign-in page with a soft failure notice.
        logger.exception("Google login redirect failed")
        return RedirectResponse(url=f"{settings.web_post_login_url}?login=failed")
    response = cast(RedirectResponse, redirect)
    if rate_guard.device_signal(request) is None:
        # First visit: give this browser an id so the per-device budget has
        # something to count next time. Issued on the way *out* so a refused
        # request never hands out a fresh one.
        rate_guard.issue_device_cookie(response, settings)
    return response


def _record_login_started(provider_key: str) -> None:
    """§13's `auth.login_started`. Carries no address, IP or return route —
    §6 AUTH-01 is enumeration-safe, and a log that recorded who was attempting
    would undo that from the inside."""
    with SessionLocal() as db:
        db.add(
            AuthenticationEvent(
                event_type=AuthEventType.LOGIN_STARTED,
                outcome=AuthEventOutcome.SUCCEEDED,
                provider_key=provider_key,
                occurred_at=clock.now(),
            )
        )
        db.commit()


_ResponseT = TypeVar("_ResponseT", RedirectResponse, JSONResponse)


def _establish_session(
    request: Request,
    settings: Settings,
    person: Person,
    resp: _ResponseT,
    *,
    auth_time: dt.datetime | None = None,
    assurance_context: dict[str, Any] | None = None,
) -> _ResponseT:
    """Issue a server-side session and put its credential in the signed cookie.

    Shared by every login method, the Google redirect flow and the password XHR
    flow alike, because §3.2's session contract does not vary by how the
    identity was proved.

    The credential exists in readable form only here: it goes straight into the
    cookie and is not returned, logged or kept. What the database holds is its
    digest, so a copy of the database yields no working sessions.
    """
    with SessionLocal() as db:
        account, identity = _account_and_identity(db, person)
        _, credential = sessions.issue_session(
            db,
            account=account,
            identity=identity,
            idle_minutes=settings.session_idle_minutes,
            absolute_hours=settings.session_absolute_hours,
            # §3.2: when the *provider* authenticated the person. Falling back
            # to now is right for the local adapter — it authenticated them
            # just now — and wrong to assume for a provider that told us
            # otherwise, which is why the callback passes its claim through.
            auth_time=auth_time,
            assurance_context=assurance_context,
        )
        accounts.record_authentication(db, account, identity)
        db.commit()

    request.session[SESSION_CREDENTIAL_KEY] = credential
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


def _issue_session(
    request: Request,
    settings: Settings,
    person: Person,
    *,
    auth_time: dt.datetime | None = None,
    assurance_context: dict[str, Any] | None = None,
) -> RedirectResponse:
    """Redirect-flow session issuance: land the browser in the SPA already
    authenticated (the Google callback)."""
    resp = RedirectResponse(url=settings.web_post_login_url)
    return _establish_session(
        request,
        settings,
        person,
        resp,
        auth_time=auth_time,
        assurance_context=assurance_context,
    )


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
        # §13: the exception may carry the token, so it goes to the correlation
        # log and not to the security log, which records only that an attempt
        # failed and why in closed terms.
        logger.exception("Google token exchange failed")
        _record_failed_login(GOOGLE_PROVIDER, "CALLBACK_INVALID")
        _count_failure(request, settings, RateLimitScope.CALLBACK_FAILURE_IP)
        return RedirectResponse(url=f"{settings.web_post_login_url}?login=failed")

    claims: dict[str, Any] | None = token.get("userinfo")
    if not claims or "sub" not in claims:
        _record_failed_login(GOOGLE_PROVIDER, "MISSING_SUBJECT")
        raise UnauthorizedError("Prijava nije uspela.")

    with SessionLocal() as db:
        # §6 AUTH-02: the registry decides whether a genuine token from this
        # issuer may be used here at all. Authlib has already proven the token
        # is genuine; that is a different question, and answering only it is how
        # a provider nobody registered ends up signing people in (§4.9).
        try:
            auth_providers.verify_callback(
                db,
                provider_key=GOOGLE_PROVIDER,
                claims=claims_for_registry(dict(claims), dict(token)),
                redirect_uri=settings.oidc_redirect_url,
            )
        except ProviderNotAllowedError:
            accounts.record_failed_login(
                db, provider_key=GOOGLE_PROVIDER, reason_code="PROVIDER_NOT_ALLOWED"
            )
            db.commit()
            _count_failure(request, settings, RateLimitScope.CALLBACK_FAILURE_IP)
            raise

        person = jit_provision(db, dict(claims))

    return _issue_session(
        request,
        settings,
        person,
        auth_time=auth_time_of(dict(claims)),
        assurance_context=assurance_of(dict(claims)),
    )


def _count_failure(
    request: Request, settings: Settings, scope: RateLimitScope
) -> None:
    """Count a failed attempt in its own transaction.

    Its own, because the request that failed has usually abandoned whatever
    transaction it had — and a failure count that rolls back with the failure
    is no count at all. Never raises: being over the limit is discovered on the
    *next* attempt, and a counter that could break the error path would turn a
    failed login into a 500.
    """
    with SessionLocal() as db, suppress(RateLimitedError):
        rate_guard.guard_failure(db, request, settings, scope)
        db.commit()


def _record_failed_login(provider_key: str, reason_code: str) -> None:
    """§13's `auth.login_failed`, on its own connection.

    Separate because the failure paths above have already given up on whatever
    transaction they were in, and a security log that only records failures
    which happened to occur inside a healthy transaction is not a security log.
    The account is never named: the attempt did not resolve to one, and guessing
    would put §11's enumeration oracle into the audit trail.
    """
    with SessionLocal() as db:
        accounts.record_failed_login(db, provider_key=provider_key, reason_code=reason_code)
        db.commit()


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
        # A password POST is itself the attempt, so it consumes the failure
        # budget up front: an attacker who is already over the limit does not
        # get one more guess checked before being told no.
        rate_guard.guard_failure(db, request, settings, RateLimitScope.PASSWORD_FAILURE_IP)
        db.commit()
    with SessionLocal() as db:
        person = authenticate_with_password(db, body.email, body.password)
    return _password_session_response(request, settings, person)


@router.post("/auth/logout", status_code=HTTP_204_NO_CONTENT, operation_id="logout")
def logout(request: Request) -> Response:
    """§6 AUTH-04: revoke exactly the session presented, and nothing else.

    The server-side revocation is the part that matters — clearing the cookie
    only affects this browser, and §6 is explicit that a credential presented
    after this must fail on the server, not merely be missing on the client.
    The other sessions of the same account stay live (M01-QA-008); ending those
    is `LogoutAll`, a different command with different proof requirements.

    With no credential, §6 allows a safe empty success: the client cleans up and
    the endpoint does not claim a revocation it did not perform.
    """
    credential = request.session.get(SESSION_CREDENTIAL_KEY)
    if credential:
        with SessionLocal() as db:
            session = db.execute(
                select(AuthSession).where(
                    AuthSession.credential_hash == sessions.hash_credential(credential)
                )
            ).scalar_one_or_none()
            if session is not None:
                sessions.revoke_session(
                    db, session, reason=SessionRevokeReason.LOGOUT
                )
                db.commit()

    request.session.clear()
    resp = Response(status_code=HTTP_204_NO_CONTENT)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp


class LogoutAllRequest(BaseModel):
    """§12: every mutation carries a stable UUID, and on HTTP the
    ``Idempotency-Key`` header must equal it exactly."""

    request_id: str = Field(min_length=1, max_length=64)


class LogoutAllResponse(BaseModel):
    revoked_sessions: int


@router.post(
    "/auth/logout-all",
    response_model=LogoutAllResponse,
    operation_id="logoutAllSessions",
)
def logout_all_sessions(
    body: LogoutAllRequest,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> LogoutAllResponse:
    """§6 AUTH-05: end every session of this account, including this one.

    The interesting part is the retry. This command revokes the credential that
    authorized it, so the identical retry arrives holding something that no
    longer authenticates anything — and §6 says it must still get the first
    result, not a 401 and not a second execution. The digest of that revoked
    credential finds exactly one receipt and returns exactly what it stored;
    it authorizes nothing else (M01-QA-020).

    Not yet done, and not pretended: §6 also wants a fresh re-authentication
    "kada je provider podržava". Neither adapter here supports step-up, so this
    requires an active session and no more — recorded rather than faked.
    """
    credential = request.session.get(SESSION_CREDENTIAL_KEY)
    if not credential:
        raise UnauthorizedError("Nedostaje prijava.")
    request_id = auth_commands.require_request_id(body.request_id, idempotency_key)

    with SessionLocal() as db:
        validated = sessions.validate_session(db, credential)
        if validated is None:
            # The session may be gone precisely because this command already
            # ran. That is the one case §6 lets a revoked credential be used
            # for: to collect the result it produced.
            replay = auth_commands.replay_for_revoked_credential(
                db,
                credential=credential,
                command=AuthCommand.LOGOUT_ALL,
                request_id=request_id,
            )
            if replay is None:
                raise UnauthorizedError("Prijava ne važi.")
            request.session.clear()
            return LogoutAllResponse(**replay["body"])

        _, account = validated
        result = auth_commands.logout_all(
            db,
            account=account,
            request_id=request_id,
            current_credential=credential,
        )
        db.commit()

    request.session.clear()
    return LogoutAllResponse(**result["body"])


def _account_and_identity(db: Session, person: Person) -> tuple[UserAccount, AuthIdentity]:
    """The account this person signs in with, and the identity that proved it.

    Refuses rather than improvises when either is missing. §2 says an ACTIVE
    account always has a linked identity, so an account without one is a broken
    invariant, and issuing a session anyway would paper over it at the one place
    that must not.
    """
    account = accounts.live_account_for_person(db, person.id)
    if account is None or account.status is not UserAccountStatus.ACTIVE:
        raise UnauthorizedError("Prijava nije uspela.")
    identity = db.execute(
        select(AuthIdentity)
        .where(
            AuthIdentity.user_account_id == account.id,
            AuthIdentity.unlinked_at.is_(None),
        )
        .order_by(AuthIdentity.last_verified_at.desc().nullslast())
    ).scalars().first()
    if identity is None:
        raise UnauthorizedError("Prijava nije uspela.")
    return account, identity
