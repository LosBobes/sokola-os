"""FastAPI application factory.

The app is a modular monolith: one process, one router per domain, one database.
Domains are wired here and nowhere else.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.common.errors import register_exception_handlers
from app.config import Settings, get_settings
from app.domains.attendance.router import router as attendance_router
from app.domains.auth.router import router as auth_router
from app.domains.billing.router import router as billing_router
from app.domains.communications.router import router as communications_router
from app.domains.events.router import router as events_router
from app.domains.groups.router import router as groups_router
from app.domains.health.router import router as health_router
from app.domains.identity.router import router as identity_router
from app.domains.internal.router import router as internal_router
from app.domains.organization.router import router as organization_router
from app.domains.parent.router import router as parent_router
from app.domains.payments.router import router as payments_router
from app.domains.people.router import router as people_router
from app.domains.reports.router import router as reports_router
from app.domains.scheduling.router import router as scheduling_router
from app.domains.structure.router import router as structure_router
from app.security.csrf import CsrfMiddleware

API_TITLE = "SOKOLA OS P0 API"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    _guard_dev_auth(settings)

    app = FastAPI(
        title=API_TITLE,
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
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
    app.include_router(organization_router)
    app.include_router(structure_router)
    app.include_router(people_router)
    app.include_router(groups_router)
    app.include_router(scheduling_router)
    app.include_router(attendance_router)
    app.include_router(billing_router)
    app.include_router(payments_router)
    app.include_router(events_router)
    app.include_router(communications_router)
    app.include_router(parent_router)
    app.include_router(reports_router)

    return app


def _guard_dev_auth(settings: Settings) -> None:
    """The dev header auth adapter must be impossible to enable in production, and
    the session secret must be changed away from the insecure default."""
    if settings.allow_insecure_dev_auth and settings.is_production_like:
        raise RuntimeError(
            "ALLOW_INSECURE_DEV_AUTH must never be enabled in staging/production."
        )
    if settings.is_production_like and "insecure" in settings.session_secret:
        raise RuntimeError("SOKOLA_SESSION_SECRET must be set in staging/production.")


app = create_app()
