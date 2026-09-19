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
from app.domains.identity.auth_enums import UserAccountStatus
from app.domains.identity.auth_models import UserAccount
from app.domains.identity.models import Person

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
    """True when the person's account may no longer sign in (M01 §3.1).

    Only ``ACTIVE`` opens or renews a session, so a suspended account is refused
    here too, not just a disabled one. A person with no ``UserAccount`` at all
    (a dev-header principal, an imported adult who has never signed in) is not
    "revoked" — there is nothing to revoke — and the session cookie is what
    vouched for them.

    This is the best revocation the signed-cookie session can do: it re-reads
    the account on every request, but it cannot tell one of a person's sessions
    from another and has no `authorization_version` to compare against. §3.2's
    server-side session store, which can, is the next M01 slice.
    """
    account = (
        db.query(UserAccount)
        .filter(UserAccount.person_id == person_id)
        .order_by(UserAccount.created_at.desc())
        .first()
    )
    return account is not None and account.status is not UserAccountStatus.ACTIVE
