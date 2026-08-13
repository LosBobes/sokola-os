"""Shared, provider-agnostic identity lookup by email.

Both Google and password registration must check this before creating a new
Person, or the same human logging in via two different methods ends up as two
duplicate accounts (see ``oidc.py::jit_provision``).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.identity.enums import AuthIdentifierType
from app.domains.identity.models import AuthAccount, AuthIdentifier, Person


def normalize_email(email: str) -> str:
    return email.strip().lower()


def find_person_by_email(db: Session, email: str) -> Person | None:
    normalized = normalize_email(email)
    stmt = (
        select(Person)
        .join(AuthAccount, AuthAccount.person_id == Person.id)
        .join(AuthIdentifier, AuthIdentifier.auth_account_id == AuthAccount.id)
        .where(
            AuthIdentifier.type == AuthIdentifierType.EMAIL,
            func.lower(AuthIdentifier.value) == normalized,
        )
    )
    return db.execute(stmt).scalar_one_or_none()
