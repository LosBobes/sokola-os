"""Principal resolution.

Two paths:

* **OIDC (production):** a bearer token is validated and its subject mapped, via
  ``AuthIdentifier`` -> ``AuthAccount`` -> ``Person``. (Token validation itself is
  a completion gate; the mapping is implemented here.)
* **Dev header adapter (local only):** ``x-sokola-person-id`` names the acting
  person directly. This path is refused unless ``allow_insecure_dev_auth`` is on,
  and that flag is refused in staging/production at startup.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.common.enums import RecordStatus
from app.common.errors import UnauthorizedError
from app.config import Settings
from app.domains.identity.enums import AuthAccountStatus, AuthIdentifierType
from app.domains.identity.models import AuthAccount, AuthIdentifier, Person

DEV_PERSON_HEADER = "x-sokola-person-id"


@dataclass(frozen=True, slots=True)
class Principal:
    person_id: str


def resolve_principal(request: Request, db: Session, settings: Settings) -> Principal:
    if settings.allow_insecure_dev_auth:
        principal = _resolve_dev_header(request, db)
        if principal is not None:
            return principal

    token = _bearer_token(request)
    if token is not None:
        return _resolve_oidc(token, db, settings)

    raise UnauthorizedError("Nedostaje prijava.")


def _resolve_dev_header(request: Request, db: Session) -> Principal | None:
    person_id = request.headers.get(DEV_PERSON_HEADER)
    if not person_id:
        return None
    person = db.get(Person, person_id)
    if person is None or person.record_status is RecordStatus.ARCHIVED:
        raise UnauthorizedError("Nepoznata osoba.")
    return Principal(person_id=person.id)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def _resolve_oidc(token: str, db: Session, settings: Settings) -> Principal:
    subject = _validate_and_extract_subject(token, settings)
    row = db.execute(
        select(Person)
        .join(AuthAccount, AuthAccount.person_id == Person.id)
        .join(AuthIdentifier, AuthIdentifier.auth_account_id == AuthAccount.id)
        .where(
            AuthIdentifier.type == AuthIdentifierType.SUBJECT,
            AuthIdentifier.value == subject,
            AuthAccount.status == AuthAccountStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if row is None:
        raise UnauthorizedError("Identitet nije povezan sa nalogom.")
    return Principal(person_id=row.id)


def _validate_and_extract_subject(token: str, settings: Settings) -> str:
    # Full JWKS signature/issuer/audience/expiry validation is a completion gate
    # (Part 11 §2). Until an issuer is configured, no token is trusted.
    if not settings.oidc_issuer:
        raise UnauthorizedError("OIDC prijava nije konfigurisana.")
    raise UnauthorizedError("Validacija tokena još nije aktivirana.")  # pragma: no cover
