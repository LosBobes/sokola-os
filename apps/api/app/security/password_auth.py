"""The built-in email+password adapter (M01 §3.2, §4.9).

§4.9 tolerates a local sign-in method only where there is an explicit adapter,
configuration and tests. This is that adapter, and it is a provider like any
other: it owns a registry row (``local-password``), it mints its own opaque
subjects, and its secret lives on an :class:`LocalPasswordCredential` hanging
off the identity — never on the account, which §3.1 forbids and which every
authorization decision reads.

The address someone types is this provider's login handle, the way a ``sub`` is
Google's. That is not the email linking §4.5 bans: a matching address never
carries an identity *across* providers here, and signing in with Google will
not find a password account.
"""

from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.common.errors import ConflictError, UnauthorizedError
from app.domains.identity.accounts import (
    create_account_with_identity,
    find_local_password_identity,
    normalize_email,
    person_for_identity,
    record_authentication,
)
from app.domains.identity.auth_enums import (
    LOCAL_PASSWORD_ISSUER,
    LOCAL_PASSWORD_PROVIDER,
)
from app.domains.identity.auth_models import LocalPasswordCredential, UserAccount
from app.domains.identity.enums import PersonIdentityStatus
from app.domains.identity.models import Person
from app.security.password import hash_password, verify_password

# A real hash to verify against when the address is unknown or has no password,
# so login takes the same time whether or not the account exists — no
# enumeration via response timing. The value it encodes is irrelevant; it never
# matches.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def register_with_password(
    db: Session, email: str, password: str, given_name: str | None, family_name: str | None
) -> Person:
    """Create a Person, an account and its first local identity, atomically.

    Raises :class:`ConflictError` if the address already signs in locally —
    setting a password on an existing account is a deliberate account-recovery
    flow (§7, and it belongs to the provider), not something registration does
    silently.
    """
    normalized = normalize_email(email)
    if find_local_password_identity(db, normalized) is not None:
        raise ConflictError("Nalog sa ovom mejl adresom već postoji. Prijavite se.")

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

    _, identity = create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=LOCAL_PASSWORD_PROVIDER,
        issuer=LOCAL_PASSWORD_ISSUER,
        subject=_new_local_subject(),
        login_email=normalized,
        # No round-trip has proved this address. §3.2 sets `email_verified_at`
        # only where the provider explicitly confirms, and this provider
        # confirms nothing.
        email_verified=False,
    )
    db.add(LocalPasswordCredential(
        auth_identity_id=identity.id, password_hash=hash_password(password)
    ))
    db.commit()
    return person


def authenticate_with_password(db: Session, email: str, password: str) -> Person:
    """Return the Person for these credentials, or raise
    :class:`UnauthorizedError`.

    The error is intentionally identical whether the address is unknown, belongs
    to a Google-only account, or the password is wrong — §11 again: no
    account-existence oracle, including through which message comes back.
    """
    identity = find_local_password_identity(db, email)
    credential = (
        db.get(LocalPasswordCredential, identity.id) if identity is not None else None
    )
    person = person_for_identity(db, identity) if identity is not None else None

    # Always run exactly one scrypt verification, against the real hash when
    # this address can sign in and a throwaway otherwise, so response time never
    # reveals whether the address exists or carries a password.
    usable = credential is not None and person is not None
    stored = credential.password_hash if usable and credential is not None else _DUMMY_HASH

    if verify_password(password, stored) and usable:
        assert identity is not None and person is not None
        account = db.get(UserAccount, identity.user_account_id)
        assert account is not None
        record_authentication(db, account, identity)
        db.commit()
        return person

    raise UnauthorizedError("Neispravna mejl adresa ili lozinka.")


def _new_local_subject() -> str:
    """This provider's subject for a new identity.

    Random rather than derived from the address, so that changing the address
    later is an attribute change and not a new identity (§7), and so nothing
    can reconstruct a subject from a person's email. Opaque to everyone,
    including us — which is what §3.2 means when it says a subject is not ours
    to reinterpret.
    """
    return f"local:{secrets.token_urlsafe(24)}"
