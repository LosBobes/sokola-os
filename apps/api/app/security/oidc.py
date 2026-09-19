"""Google OIDC: the Authlib client and the account/identity link.

We store identity links only — the Google ``sub`` under
``https://accounts.google.com``, on an :class:`AuthIdentity` owned by a
:class:`UserAccount`. No password hashes, no provider tokens, no reset tokens.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import json
from typing import Any

from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session

from app.common.errors import ForbiddenError
from app.config import get_settings
from app.domains.identity import auth_providers
from app.domains.identity.accounts import (
    create_account_with_identity,
    find_identity,
    normalize_email,
    person_for_identity,
    record_authentication,
)
from app.domains.identity.auth_enums import GOOGLE_ISSUER, GOOGLE_PROVIDER
from app.domains.identity.auth_models import UserAccount
from app.domains.identity.enums import PersonIdentityStatus
from app.domains.identity.models import Person

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


def id_token_algorithm(token: dict[str, Any]) -> str | None:
    """The `alg` from the ID token's header, or ``None`` if unreadable.

    Read without verifying, because the adapter has already verified the token —
    this is for the registry's allowlist check, not for trust. ``None`` means
    "could not tell", and `verify_callback` treats that as "do not check" rather
    than "allow anything": the adapter's own validation is what rejects a bad
    algorithm, and the registry's list is defence in depth on top of it.
    """
    raw = token.get("id_token")
    if not isinstance(raw, str) or raw.count(".") != 2:
        return None
    header_b64 = raw.split(".", 1)[0]
    padding = "=" * (-len(header_b64) % 4)
    try:
        header = json.loads(base64.urlsafe_b64decode(header_b64 + padding))
    except (ValueError, binascii.Error):
        return None
    alg = header.get("alg")
    return alg if isinstance(alg, str) else None


def claims_for_registry(
    claims: dict[str, Any], token: dict[str, Any]
) -> auth_providers.CallbackClaims:
    """Narrow the token down to what the registry has an opinion about.

    `aud` may be a string or a list — the spec allows both, and a provider that
    sends a list of one is not sending a different audience. Anything beyond one
    entry is refused here by taking only the first: a token addressed to several
    audiences is not one this deployment should accept on the strength of the
    others.
    """
    audience = claims.get("aud")
    if isinstance(audience, list):
        audience = audience[0] if len(audience) == 1 else ""
    return auth_providers.CallbackClaims(
        issuer=str(claims.get("iss", "")),
        audience=str(audience or ""),
        subject=str(claims.get("sub", "")),
        algorithm=id_token_algorithm(token),
    )


def auth_time_of(claims: dict[str, Any]) -> dt.datetime | None:
    """§3.2's `auth_time`: when the *provider* authenticated the human.

    Not when we issued the session. §6 AUTH-06/07 require a fresh
    re-authentication, and "fresh" has to mean fresh at the provider — a value
    taken from our own clock would make every session look freshly proven.
    """
    raw = claims.get("auth_time")
    if not isinstance(raw, int | float):
        return None
    try:
        return dt.datetime.fromtimestamp(float(raw), tz=dt.UTC)
    except (OverflowError, OSError, ValueError):
        return None


def jit_provision(db: Session, claims: dict[str, Any]) -> Person:
    """Return the Person for these verified ID-token claims.

    Idempotent on ``issuer + sub``, and *only* on that. An email that matches an
    existing account does not link this subject to it: §4.5 is explicit that a
    matching address links nothing on its own, because an address is something a
    provider asserts and an attacker can often arrange to have asserted.
    """
    subject = claims["sub"]
    identity = find_identity(db, GOOGLE_ISSUER, subject)
    if identity is not None:
        person = person_for_identity(db, identity)
        if person is None:
            # A subject we know, on an account that may no longer sign in. §11
            # keeps `ACCOUNT_INACTIVE` free of the reason, so this says no more
            # than an unknown subject would.
            db.rollback()
            raise ForbiddenError("Prijava trenutno nije moguća za ovaj nalog.")
        account = db.get(UserAccount, identity.user_account_id)
        assert account is not None
        record_authentication(db, account, identity)
        db.commit()
        return person

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

    create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
        login_email=normalize_email(email) if email else None,
        email_verified=bool(claims.get("email_verified")),
    )
    db.commit()
    return person
