"""M01 §3.2, §4.9, §6 AUTH-02 and §13: the callback consults the registry.

Until now the registry existed and nothing read it. An adapter someone
configured but nobody registered could sign people in, which is the difference
between a fail-closed registry and a decorative one — §4.9 is explicit that a
sign-in method without an explicit adapter, configuration *and* tests does not
exist however the deployment is set up.

The adapter's own token validation still happens and still matters. It proves
the token is genuine; the registry answers a different question, which is
whether a genuine token from that issuer may be used *here*. Every refusal
returns the same error, because §11 keeps `PROVIDER_NOT_ALLOWED` free of
configuration detail: telling an attacker which check rejected them tells them
what to change.
"""

from __future__ import annotations

import base64
import datetime as dt
import json

import pytest
from app.common.errors import ProviderNotAllowedError, UnauthorizedError
from app.config import Settings, get_settings
from app.domains.identity import auth_providers
from app.domains.identity.auth_enums import (
    GOOGLE_ISSUER,
    GOOGLE_PROVIDER,
    LOCAL_PASSWORD_PROVIDER,
    AuthProviderStatus,
)
from app.domains.identity.auth_models import (
    AuthenticationEvent,
    AuthProviderRegistration,
)
from app.domains.identity.auth_providers import CallbackClaims, verify_callback
from app.security.oidc import auth_time_of, claims_for_registry, id_token_algorithm
from app.security.password_auth import authenticate_with_password, register_with_password
from sqlalchemy import select
from sqlalchemy.orm import Session

AUDIENCE = "123-abc.apps.googleusercontent.com"
REDIRECT = "https://example.invalid/api/auth/google/callback"


def _registered(db: Session, **overrides: object) -> AuthProviderRegistration:
    google = db.get(AuthProviderRegistration, GOOGLE_PROVIDER)
    assert google is not None
    google.allowed_audiences = [AUDIENCE]
    google.allowed_redirect_uris = [REDIRECT]
    for key, value in overrides.items():
        setattr(google, key, value)
    db.commit()
    return google


def _claims(**overrides: object) -> CallbackClaims:
    base = {
        "issuer": GOOGLE_ISSUER,
        "audience": AUDIENCE,
        "subject": "google-sub-1",
        "algorithm": "RS256",
    }
    base.update(overrides)
    return CallbackClaims(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# §6 AUTH-02 — the registry decides
# ---------------------------------------------------------------------------


def test_a_registered_callback_passes(db: Session) -> None:
    _registered(db)
    assert (
        verify_callback(
            db,
            provider_key=GOOGLE_PROVIDER,
            claims=_claims(),
            redirect_uri=REDIRECT,
        ).provider_key
        == GOOGLE_PROVIDER
    )


def test_an_unregistered_provider_is_refused(db: Session) -> None:
    """§4.9: an adapter with no registration is not a provider, whatever the
    deployment config says."""
    with pytest.raises(ProviderNotAllowedError):
        verify_callback(db, provider_key="facebook", claims=_claims())


def test_a_disabled_provider_is_refused(db: Session) -> None:
    """Disabling is an audited config decision and it takes effect at the
    callback, not at the next restart."""
    _registered(db, status=AuthProviderStatus.DISABLED)
    with pytest.raises(ProviderNotAllowedError):
        verify_callback(db, provider_key=GOOGLE_PROVIDER, claims=_claims())


@pytest.mark.parametrize(
    "issuer",
    [
        GOOGLE_ISSUER + "/",
        GOOGLE_ISSUER.upper(),
        GOOGLE_ISSUER.replace("https", "http"),
        "https://accounts.google.com.evil.invalid",
    ],
)
def test_the_issuer_must_match_byte_for_byte(db: Session, issuer: str) -> None:
    """M01-QA-019. Every tolerance is a second spelling of the issuer, and an
    attacker who controls one spelling controls which registration applies."""
    _registered(db)
    with pytest.raises(ProviderNotAllowedError):
        verify_callback(
            db, provider_key=GOOGLE_PROVIDER, claims=_claims(issuer=issuer)
        )


def test_an_unlisted_audience_is_refused(db: Session) -> None:
    """A token addressed to someone else's client is someone else's token."""
    _registered(db)
    with pytest.raises(ProviderNotAllowedError):
        verify_callback(
            db,
            provider_key=GOOGLE_PROVIDER,
            claims=_claims(audience="999-other.apps.googleusercontent.com"),
        )


def test_an_empty_audience_allowlist_refuses_everything(db: Session) -> None:
    """The intended reading of "unconfigured".

    A deployment that has not declared its client id has not declared it, and
    an empty list that meant "anything" would make the fail-closed registry
    fail open exactly where it was never configured.
    """
    _registered(db, allowed_audiences=[])
    with pytest.raises(ProviderNotAllowedError):
        verify_callback(db, provider_key=GOOGLE_PROVIDER, claims=_claims())


def test_an_unlisted_algorithm_is_refused(db: Session) -> None:
    _registered(db)
    with pytest.raises(ProviderNotAllowedError):
        verify_callback(
            db, provider_key=GOOGLE_PROVIDER, claims=_claims(algorithm="none")
        )


def test_an_unlisted_redirect_is_refused(db: Session) -> None:
    _registered(db)
    with pytest.raises(ProviderNotAllowedError):
        verify_callback(
            db,
            provider_key=GOOGLE_PROVIDER,
            claims=_claims(),
            redirect_uri="https://attacker.invalid/callback",
        )


def test_every_refusal_says_the_same_thing(db: Session) -> None:
    """§11: "bez detalja konfiguracije". Four different reasons, one message."""
    _registered(db)
    messages = set()
    for claims, redirect in (
        (_claims(issuer="https://evil.invalid"), REDIRECT),
        (_claims(audience="other"), REDIRECT),
        (_claims(algorithm="none"), REDIRECT),
        (_claims(), "https://attacker.invalid/cb"),
    ):
        with pytest.raises(ProviderNotAllowedError) as caught:
            verify_callback(
                db,
                provider_key=GOOGLE_PROVIDER,
                claims=claims,
                redirect_uri=redirect,
            )
        messages.add(caught.value.message)
    assert len(messages) == 1


def test_an_unreadable_algorithm_does_not_open_the_gate(db: Session) -> None:
    """`None` means "could not tell", and the other checks still apply.

    The adapter's own validation is what rejects a bad algorithm; the registry's
    list is defence in depth on top of it, and defence in depth that fails
    closed on an unreadable header would reject valid logins for a header we
    only read as a courtesy.
    """
    _registered(db)
    assert verify_callback(
        db, provider_key=GOOGLE_PROVIDER, claims=_claims(algorithm=None)
    )
    with pytest.raises(ProviderNotAllowedError):
        verify_callback(
            db,
            provider_key=GOOGLE_PROVIDER,
            claims=_claims(algorithm=None, audience="other"),
        )


# ---------------------------------------------------------------------------
# Reading the token, without trusting it
# ---------------------------------------------------------------------------


def _jwt(header: dict[str, object]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    return f"{encoded}.payload.signature"


def test_the_algorithm_is_read_from_the_header() -> None:
    assert id_token_algorithm({"id_token": _jwt({"alg": "RS256"})}) == "RS256"
    assert id_token_algorithm({"id_token": _jwt({"alg": "none"})}) == "none"


@pytest.mark.parametrize(
    "token",
    [
        {},
        {"id_token": None},
        {"id_token": "not-a-jwt"},
        {"id_token": "a.b"},
        {"id_token": "!!!.payload.sig"},
        {"id_token": _jwt({"typ": "JWT"})},
    ],
)
def test_an_unreadable_header_is_none_not_a_crash(token: dict) -> None:
    """This parses attacker-influenced bytes, so it has to survive all of them.
    A verification helper that can raise is a login that can 500."""
    assert id_token_algorithm(token) is None


def test_a_single_element_audience_list_is_that_audience() -> None:
    """Providers are allowed to send `aud` as a list, and a list of one is not
    a different audience."""
    claims = claims_for_registry({"iss": "i", "aud": [AUDIENCE], "sub": "s"}, {})
    assert claims.audience == AUDIENCE


def test_a_multi_audience_token_is_not_accepted_on_one_of_them() -> None:
    """A token addressed to several audiences is not one this deployment should
    accept on the strength of the others — so it resolves to an audience that
    matches no allowlist."""
    claims = claims_for_registry(
        {"iss": "i", "aud": [AUDIENCE, "other"], "sub": "s"}, {}
    )
    assert claims.audience == ""


def test_auth_time_comes_from_the_provider() -> None:
    """§3.2: when the provider authenticated the human, not when we issued the
    session. A value from our own clock would make every session look freshly
    proven, which is exactly what §6 AUTH-06/07 need to be able to disbelieve."""
    moment = dt.datetime(2026, 9, 19, 10, 30, tzinfo=dt.UTC)
    assert auth_time_of({"auth_time": moment.timestamp()}) == moment


@pytest.mark.parametrize(
    "claims", [{}, {"auth_time": None}, {"auth_time": "yesterday"}, {"auth_time": 1e30}]
)
def test_a_missing_or_absurd_auth_time_is_none(claims: dict) -> None:
    assert auth_time_of(claims) is None


# ---------------------------------------------------------------------------
# §4.9 — the local adapter is off unless asked for
# ---------------------------------------------------------------------------


def test_password_auth_is_off_by_default() -> None:
    """§4.9: "Podrazumevano je OFF."

    Asserted against the field's declared default rather than a constructed
    `Settings`, because constructing one still reads the environment — and the
    test suite deliberately turns the adapter on, so that would only prove that
    it did.
    """
    assert Settings.model_fields["password_auth_enabled"].default is False


def test_this_deployment_turned_it_on_explicitly() -> None:
    """Which is the whole distinction: a deployment that said yes, rather than
    one that never said no."""
    assert get_settings().password_auth_enabled is True


# ---------------------------------------------------------------------------
# §13 — what the security log records
# ---------------------------------------------------------------------------


def test_a_failed_password_login_is_recorded(db: Session) -> None:
    register_with_password(db, "pao@example.invalid", "dovoljnodugo1", "P", "A")
    with pytest.raises(UnauthorizedError):
        authenticate_with_password(db, "pao@example.invalid", "pogresna")

    events = db.execute(
        select(AuthenticationEvent).where(
            AuthenticationEvent.event_type == "auth.login_failed"
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].provider_key == LOCAL_PASSWORD_PROVIDER
    assert events[0].reason_code == "INVALID_CREDENTIALS"


def test_an_unknown_address_is_not_attributed_to_an_account(db: Session) -> None:
    """§11's enumeration rule, applied to the audit trail.

    A reason code or an account id that distinguished "no such address" from
    "wrong password" would rebuild inside the log the oracle the response body
    withholds — and the log is read by more people than the response is.
    """
    with pytest.raises(UnauthorizedError):
        authenticate_with_password(db, "niko@example.invalid", "bilosta")

    event = db.execute(
        select(AuthenticationEvent).where(
            AuthenticationEvent.event_type == "auth.login_failed"
        )
    ).scalar_one()
    assert event.user_account_id is None
    assert event.reason_code == "INVALID_CREDENTIALS"


def test_the_security_log_has_nowhere_to_put_a_token_or_an_address(db: Session) -> None:
    """§13 forbids raw email, IP, token, cookie, authorization header and
    provider payload. The strongest form of that is having no column for them."""
    from sqlalchemy import inspect

    columns = {c.name for c in inspect(AuthenticationEvent).columns}
    assert columns & {
        "email",
        "ip",
        "ip_address",
        "token",
        "id_token",
        "access_token",
        "cookie",
        "authorization",
        "payload",
        "user_agent",
    } == set()


def test_provider_registrations_survive_the_boot_sync(db: Session) -> None:
    """The sync writes deployment allowlists; it must not undo an operator's
    audiences by re-seeding over them."""
    _registered(db)
    auth_providers.ensure_builtin_providers(db)
    db.commit()
    google = db.get(AuthProviderRegistration, GOOGLE_PROVIDER)
    assert list(google.allowed_audiences) == [AUDIENCE]
