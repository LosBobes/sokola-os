"""FastAPI application factory.

The app is a modular monolith: one process, one router per domain, one database.
Domains are wired here and nowhere else.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.application.tenant_router import router as tenancy_router
from app.common.errors import register_exception_handlers
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.domains.attendance.router import router as attendance_router
from app.domains.auth.router import router as auth_router
from app.domains.billing.router import router as billing_router
from app.domains.communications.router import router as communications_router
from app.domains.data_import.router import router as data_import_router
from app.domains.documents.router import router as documents_router
from app.domains.events.router import router as events_router
from app.domains.groups.router import router as groups_router
from app.domains.health.router import router as health_router
from app.domains.identity.auth_providers import sync_provider_registry
from app.domains.identity.router import router as identity_router
from app.domains.internal.router import router as internal_router
from app.domains.onboarding.router import router as onboarding_router
from app.domains.parent.router import router as parent_router
from app.domains.payments.router import router as payments_router
from app.domains.people.router import router as people_router
from app.domains.privacy.router import router as privacy_router
from app.domains.progress.router import router as progress_router
from app.domains.reports.router import router as reports_router
from app.domains.scheduling.router import router as scheduling_router
from app.domains.school.router import router as school_router
from app.domains.search.router import router as search_router
from app.domains.structure.router import router as structure_router
from app.platform import crypto
from app.security.csrf import CsrfMiddleware

API_TITLE = "SOKOLA OS P0 API"


def create_app(settings: Settings | None = None) -> FastAPI:
    # Without this, app-level logger.info/warning calls are silently dropped
    # under uvicorn's default root log level. Idempotent, safe to call once
    # per create_app().
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    settings = settings or get_settings()
    _guard_dev_auth(settings)
    _guard_contact_keys(settings)

    app = FastAPI(
        title=API_TITLE,
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
    )

    # Middleware runs outermost-last-added. We want, request-inward:
    #   CORS -> Session -> CSRF -> app
    # so Session is available when CSRF checks the cookie. Add in reverse.
    app.add_middleware(CsrfMiddleware)

    # Signed session cookie backing OIDC login. Secure cookies in prod-like envs.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site="lax",
        https_only=settings.is_production_like,
    )

    # Restricted CORS. Production origins are injected, never wildcarded.
    allowed_origins = ["http://localhost:5173"] if settings.environment == "local" else []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(internal_router)
    app.include_router(identity_router)
    app.include_router(school_router)
    app.include_router(onboarding_router)
    app.include_router(structure_router)
    app.include_router(people_router)
    app.include_router(groups_router)
    app.include_router(scheduling_router)
    app.include_router(attendance_router)
    app.include_router(progress_router)
    app.include_router(billing_router)
    app.include_router(payments_router)
    app.include_router(events_router)
    app.include_router(communications_router)
    app.include_router(documents_router)
    app.include_router(parent_router)
    app.include_router(privacy_router)
    app.include_router(data_import_router)
    app.include_router(tenancy_router)
    app.include_router(search_router)
    app.include_router(reports_router)

    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Reconcile the M01 provider registry before the first request.

    The registry decides which issuers may tell us who somebody is (M01 §3.2),
    and its audience and redirect allowlists are deployment facts. Doing this at
    boot rather than at first callback means a misconfigured deployment is
    visible on start, not on someone's first sign-in attempt.
    """
    with SessionLocal() as db:
        sync_provider_registry(db, get_settings())
    yield


def _guard_dev_auth(settings: Settings) -> None:
    """The dev header auth adapter must be impossible to enable in production, and
    the session secret must be changed away from the insecure default."""
    if settings.allow_insecure_dev_auth and settings.is_production_like:
        raise RuntimeError(
            "ALLOW_INSECURE_DEV_AUTH must never be enabled in staging/production."
        )
    if settings.is_production_like and "insecure" in settings.session_secret:
        raise RuntimeError("SOKOLA_SESSION_SECRET must be set in staging/production.")
    if (
        settings.is_production_like
        and settings.password_auth_enabled
        and "insecure" in settings.password_pepper
    ):
        raise RuntimeError("SOKOLA_PASSWORD_PEPPER must be set in staging/production.")


def _guard_contact_keys(settings: Settings) -> None:
    """Contact keyrings must parse at boot, and must not be the dev defaults.

    Parsing here rather than on first use turns a mistyped key into a refused
    start, instead of a school that provisions fine and whose contact column
    cannot be read back. And a published default key protecting real contacts is
    the same failure as a published session secret, so it is refused the same way.
    """
    for what, raw in (
        ("SOKOLA_CONTACT_ENCRYPTION_KEYS", settings.contact_encryption_keys),
        ("SOKOLA_CONTACT_FINGERPRINT_KEYS", settings.contact_fingerprint_keys),
    ):
        keyring = crypto.parse_keyring(raw, what=what)
        if settings.is_production_like and any(
            b"insecure" in key for key in keyring.keys.values()
        ):
            # The marker is in the key *material*, not in the base64 text, so
            # re-encoding the published default does not get past this.
            raise RuntimeError(f"{what} must be set in staging/production.")


app = create_app()
