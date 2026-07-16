"""FastAPI application factory.

The app is a modular monolith: one process, one router per domain, one database.
Domains are wired here and nowhere else.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.common.errors import register_exception_handlers
from app.config import Settings, get_settings
from app.domains.attendance.router import router as attendance_router
from app.domains.billing.router import router as billing_router
from app.domains.groups.router import router as groups_router
from app.domains.health.router import router as health_router
from app.domains.identity.router import router as identity_router
from app.domains.organization.router import router as organization_router
from app.domains.payments.router import router as payments_router
from app.domains.people.router import router as people_router
from app.domains.scheduling.router import router as scheduling_router

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
    app.include_router(identity_router)
    app.include_router(organization_router)
    app.include_router(people_router)
    app.include_router(groups_router)
    app.include_router(scheduling_router)
    app.include_router(attendance_router)
    app.include_router(billing_router)
    app.include_router(payments_router)

    return app


def _guard_dev_auth(settings: Settings) -> None:
    """The dev header auth adapter must be impossible to enable in production."""
    if settings.allow_insecure_dev_auth and settings.is_production_like:
        raise RuntimeError(
            "ALLOW_INSECURE_DEV_AUTH must never be enabled in staging/production."
        )


app = create_app()
