"""Google OIDC: the Authlib client and just-in-time Person provisioning.

We store only identity links — the Google ``sub`` mapped to a Person via
``AuthAccount`` / ``AuthIdentifier``. No password hashes or reset tokens ever.
"""

from __future__ import annotations

from typing import Any

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domains.identity.enums import (
    AuthAccountStatus,
    AuthIdentifierType,
    PersonIdentityStatus,
)
from app.domains.identity.models import AuthAccount, AuthIdentifier, Person

_oauth: OAuth | None = None


def get_oauth() -> OAuth:
    """Lazily build the OAuth registry from settings (Google via discovery)."""
    global _oauth
    if _oauth is None:
        settings = get_settings()
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url=settings.google_discovery_url,
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth = oauth
    return _oauth


def _find_by_subject(db: Session, subject: str) -> Person | None:
    stmt = (
        select(Person)
        .join(AuthAccount, AuthAccount.person_id == Person.id)
        .join(AuthIdentifier, AuthIdentifier.auth_account_id == AuthAccount.id)
        .where(
            AuthIdentifier.type == AuthIdentifierType.SUBJECT,
            AuthIdentifier.value == subject,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def jit_provision(db: Session, claims: dict[str, Any]) -> Person:
    """Return the Person for these verified ID-token claims, creating the
    identity link on first login. Idempotent on the Google ``sub``."""
    subject = claims["sub"]
    existing = _find_by_subject(db, subject)
    if existing is not None:
        return existing

    email = claims.get("email")
    given = (claims.get("given_name") or "").strip()
    family = (claims.get("family_name") or "").strip()
    display = (claims.get("name") or f"{given} {family}").strip() or email or "Korisnik"

    person = Person(
        given_name=given or display,
        family_name=family or "",
        display_name=display,
        identity_status=PersonIdentityStatus.VERIFIED,
    )
    db.add(person)
    db.flush()

    account = AuthAccount(
        person_id=person.id, provider="google", status=AuthAccountStatus.ACTIVE
    )
    db.add(account)
    db.flush()

    db.add(
        AuthIdentifier(
            auth_account_id=account.id, type=AuthIdentifierType.SUBJECT, value=subject
        )
    )
    if email and not _email_taken(db, email):
        db.add(
            AuthIdentifier(
                auth_account_id=account.id, type=AuthIdentifierType.EMAIL, value=email
            )
        )
    db.commit()
    return person


def _email_taken(db: Session, email: str) -> bool:
    stmt = select(AuthIdentifier.id).where(
        AuthIdentifier.type == AuthIdentifierType.EMAIL, AuthIdentifier.value == email
    )
    return db.execute(stmt).scalar_one_or_none() is not None
