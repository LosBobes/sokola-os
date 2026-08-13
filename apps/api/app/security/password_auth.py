"""Email + password authentication.

Registration provisions a Person the same way OIDC does, but stores a
password hash on the :class:`AuthAccount` so the person can sign in directly , 
no email round-trip, no external provider. Login verifies that hash.

Deduplication is shared with every other method via ``find_person_by_email``:
one human, one Person, regardless of how they first arrived.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, UnauthorizedError
from app.domains.identity.enums import (
    AuthAccountStatus,
    AuthIdentifierType,
    PersonIdentityStatus,
)
from app.domains.identity.models import AuthAccount, AuthIdentifier, Person
from app.security.identity_lookup import find_person_by_email, normalize_email
from app.security.password import hash_password, verify_password

# A real hash to verify against when the email is unknown or has no password, so
# login takes the same time whether or not the account exists, no enumeration
# via response timing. The value it encodes is irrelevant; it never matches.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def register_with_password(
    db: Session, email: str, password: str, given_name: str | None, family_name: str | None
) -> Person:
    """Create a Person with an email+password credential. Raises
    :class:`ConflictError` if the email already resolves to an identity , 
    setting a password on an existing account is a deliberate account-recovery
    flow, not something registration does silently."""
    if find_person_by_email(db, email) is not None:
        raise ConflictError("Nalog sa ovom mejl adresom već postoji. Prijavite se.")

    normalized = normalize_email(email)
    given = (given_name or "").strip()
    family = (family_name or "").strip()
    display = f"{given} {family}".strip() or normalized

    person = Person(
        given_name=given or display,
        family_name=family or "",
        display_name=display,
        identity_status=PersonIdentityStatus.VERIFIED,
    )
    db.add(person)
    db.flush()

    account = AuthAccount(
        person_id=person.id,
        provider="password",
        status=AuthAccountStatus.ACTIVE,
        password_hash=hash_password(password),
    )
    db.add(account)
    db.flush()

    db.add(
        AuthIdentifier(auth_account_id=account.id, type=AuthIdentifierType.EMAIL, value=normalized)
    )
    db.commit()
    return person


def authenticate_with_password(db: Session, email: str, password: str) -> Person:
    """Return the Person for these credentials, or raise
    :class:`UnauthorizedError`. The error is intentionally identical whether the
    email is unknown, has no password set (Google only), or the
    password is wrong, no account-existence oracle."""
    person = find_person_by_email(db, email)
    account = (
        db.execute(
            select(AuthAccount).where(AuthAccount.person_id == person.id)
        ).scalar_one_or_none()
        if person is not None
        else None
    )

    # Always run one scrypt verification, against the real hash when the account
    # can log in with a password, against a throwaway hash otherwise, so
    # response time never reveals whether the email exists or carries a password.
    stored = _DUMMY_HASH
    if account is not None and account.status is AuthAccountStatus.ACTIVE and account.password_hash:
        stored = account.password_hash

    if verify_password(password, stored) and person is not None and stored is not _DUMMY_HASH:
        return person

    raise UnauthorizedError("Neispravna mejl adresa ili lozinka.")
