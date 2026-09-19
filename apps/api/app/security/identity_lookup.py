"""Shared, provider-agnostic person lookup by sign-in address.

Kept as a module of its own because who may call it matters. §4.5 forbids an
email match from linking an account or merging two people, so this returns the
person behind an address only for adapters that own that address — today, the
local password adapter, whose login handle *is* the address.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.identity.accounts import (
    find_local_password_identity,
    normalize_email,
)
from app.domains.identity.auth_models import UserAccount
from app.domains.identity.models import Person

__all__ = ["find_person_by_login_email", "normalize_email"]


def find_person_by_login_email(db: Session, email: str) -> Person | None:
    """The person who signs in locally with this address, whatever their account
    status. Status is the caller's decision: a suspended account must produce
    the same generic refusal as an unknown address (§11), not a different one."""
    identity = find_local_password_identity(db, email)
    if identity is None:
        return None
    account = db.get(UserAccount, identity.user_account_id)
    return db.get(Person, account.person_id) if account is not None else None
