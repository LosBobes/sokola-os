"""Principal resolution, who is making the request.

Order:

1. **Dev header adapter** (local only): ``x-sokola-person-id`` names the acting
   person. Refused unless ``allow_insecure_dev_auth`` is on (and that flag is
   refused in staging/production at startup).
2. **OIDC session**: a signed session cookie carrying ``person_id``, established
   by the Google login callback (see :mod:`app.security.oidc`).

The acting school/role is resolved separately and re-checked on every
request (see :mod:`app.security.deps`).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session
from starlette.requests import Request

from app.common.enums import RecordStatus
from app.common.errors import UnauthorizedError
from app.config import Settings
from app.domains.identity.enums import AuthAccountStatus
from app.domains.identity.models import AuthAccount, Person

DEV_PERSON_HEADER = "x-sokola-person-id"


@dataclass(frozen=True, slots=True)
class Principal:
    person_id: str


def resolve_principal(request: Request, db: Session, settings: Settings) -> Principal:
    if settings.allow_insecure_dev_auth:
        principal = _resolve_dev_header(request, db)
        if principal is not None:
            return principal

    principal = _resolve_session(request, db)
    if principal is not None:
        return principal

    raise UnauthorizedError("Nedostaje prijava.")


def _resolve_dev_header(request: Request, db: Session) -> Principal | None:
    person_id = request.headers.get(DEV_PERSON_HEADER)
    if not person_id:
        return None
    if not _is_active_person(db, person_id):
        raise UnauthorizedError("Nepoznata osoba.")
    return Principal(person_id=person_id)


def _resolve_session(request: Request, db: Session) -> Principal | None:
    # Read from the raw scope so this works with or without SessionMiddleware
    # installed (e.g. in unit tests that construct a bare Request).
    session = request.scope.get("session") or {}
    person_id = session.get("person_id")
    if not person_id:
        return None
    if not _is_active_person(db, person_id):
        return None
    # Revocation: a Google session outlives any single request, so honour an
    # account that has since been disabled (deprovisioned / access revoked).
    if _account_revoked(db, person_id):
        return None
    return Principal(person_id=person_id)


def _is_active_person(db: Session, person_id: str) -> bool:
    person = db.get(Person, person_id)
    return person is not None and person.record_status is not RecordStatus.ARCHIVED


def _account_revoked(db: Session, person_id: str) -> bool:
    """True when the person's external auth account has been disabled. A person
    with no ``AuthAccount`` (e.g. dev-only) is never considered revoked here."""
    account = (
        db.query(AuthAccount).filter(AuthAccount.person_id == person_id).one_or_none()
    )
    return account is not None and account.status is AuthAccountStatus.DISABLED
