"""M01 §3.2: reading and reconciling the fail-closed provider registry.

The registry answers one question — "is this issuer allowed to tell us who
somebody is?" — and answers it from the database, not from the adapter that is
asking. An adapter that is configured but has no ``ACTIVE`` row here is not a
provider; §11 calls that ``PROVIDER_NOT_ALLOWED``.

Audiences and redirect URIs are deployment facts, so they are reconciled from
settings at boot rather than written into the migration. The reconciliation is
one-directional and narrow: it may set the allowlists for an adapter this
deployment has configured, and it may never mark a provider ``ACTIVE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ProviderNotAllowedError
from app.config import Settings
from app.domains.identity.auth_enums import (
    GOOGLE_ISSUER,
    GOOGLE_PROVIDER,
    LOCAL_PASSWORD_ISSUER,
    LOCAL_PASSWORD_PROVIDER,
    AuthProviderStatus,
)
from app.domains.identity.auth_models import AuthProviderRegistration

#: The single message every registry refusal gives. §11 keeps
#: `PROVIDER_NOT_ALLOWED` free of configuration detail, and naming which
#: check failed would tell an attacker what to change.
PROVIDER_REFUSAL = "Prijava preko ovog provajdera nije dozvoljena."


class BuiltinProvider(NamedTuple):
    """One adapter this codebase ships, as the registry should first see it."""

    provider_key: str
    issuer: str
    allowed_algorithms: tuple[str, ...]
    discovery_url: str | None


#: The adapters this codebase actually ships. A provider that is not here has no
#: adapter, and §4.9 is explicit that a sign-in method without one does not
#: exist however the deployment is configured.
#:
#: Audiences and redirect URIs are absent on purpose: they are deployment facts,
#: reconciled by `sync_provider_registry`. An empty allowlist fails closed; a
#: guessed one fails open.
BUILTIN_PROVIDERS: tuple[BuiltinProvider, ...] = (
    BuiltinProvider(
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        allowed_algorithms=("RS256",),
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
    ),
    BuiltinProvider(
        provider_key=LOCAL_PASSWORD_PROVIDER,
        issuer=LOCAL_PASSWORD_ISSUER,
        allowed_algorithms=("scrypt",),
        discovery_url=None,
    ),
)


def active_registration(db: Session, provider_key: str) -> AuthProviderRegistration | None:
    """The one ACTIVE registration for this adapter, or ``None``.

    ``None`` is the fail-closed answer, and callers must treat it as a refusal
    rather than as "no policy configured".
    """
    stmt = select(AuthProviderRegistration).where(
        AuthProviderRegistration.provider_key == provider_key,
        AuthProviderRegistration.status == AuthProviderStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def registration_for_issuer(db: Session, issuer: str) -> AuthProviderRegistration | None:
    """§3.2: the callback's issuer must match an ACTIVE registration *exactly*.

    Compared with ``==`` against the stored text, deliberately: no trimming, no
    case folding, no trailing-slash tolerance. `https://accounts.google.com/`
    is a different issuer from `https://accounts.google.com`, and a system that
    smooths that over is a system where an attacker gets to choose which
    smoothing applies.
    """
    stmt = select(AuthProviderRegistration).where(
        AuthProviderRegistration.issuer == issuer,
        AuthProviderRegistration.status == AuthProviderStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def ensure_builtin_providers(db: Session) -> None:
    """Create any missing built-in registration, leaving existing ones alone.

    Only the row's existence is asserted. Everything an operator can decide —
    status above all — is left where they put it, so a provider someone
    disabled does not come back on the next restart.
    """
    for spec in BUILTIN_PROVIDERS:
        if db.get(AuthProviderRegistration, spec.provider_key) is not None:
            continue
        db.add(
            AuthProviderRegistration(
                provider_key=spec.provider_key,
                issuer=spec.issuer,
                allowed_audiences=[],
                allowed_redirect_uris=[],
                allowed_algorithms=list(spec.allowed_algorithms),
                discovery_url=spec.discovery_url,
                status=AuthProviderStatus.ACTIVE,
                config_revision=1,
            )
        )


def sync_provider_registry(db: Session, settings: Settings) -> None:
    """Reconcile the deployment-specific allowlists into the registry.

    Only the audience and redirect allowlists move, and only for a provider this
    deployment has actually configured. Status stays where an operator put it:
    turning a provider on is an audited config decision (§3.2), and a process
    that could do it on restart would make the registry a copy of the
    environment rather than a control over it.
    """
    ensure_builtin_providers(db)
    db.flush()

    google = db.get(AuthProviderRegistration, GOOGLE_PROVIDER)
    if google is not None and settings.oidc_enabled:
        audiences = [settings.google_client_id] if settings.google_client_id else []
        redirects = [settings.oidc_redirect_url] if settings.oidc_redirect_url else []
        _apply(google, audiences=audiences, redirects=redirects)

    local = db.get(AuthProviderRegistration, LOCAL_PASSWORD_PROVIDER)
    if local is not None:
        # The local adapter has no audience and no redirect: the "callback" is
        # the same request that carried the password.
        _apply(local, audiences=[], redirects=[])

    db.commit()


def _apply(
    registration: AuthProviderRegistration,
    *,
    audiences: list[str],
    redirects: list[str],
) -> None:
    if (
        list(registration.allowed_audiences) == audiences
        and list(registration.allowed_redirect_uris) == redirects
    ):
        return
    registration.allowed_audiences = audiences
    registration.allowed_redirect_uris = redirects
    registration.config_revision += 1


@dataclass(frozen=True, slots=True)
class CallbackClaims:
    """What an adapter presents for registry checking (M01 §6 AUTH-02).

    Deliberately not the token, and deliberately not a dict: a dict would carry
    whatever the provider sent, and §13 forbids the raw payload reaching the
    audit trail or the logs. These four fields are the ones the registry has an
    opinion about.
    """

    issuer: str
    audience: str
    subject: str
    algorithm: str | None = None


def verify_callback(
    db: Session,
    *,
    provider_key: str,
    claims: CallbackClaims,
    redirect_uri: str | None = None,
) -> AuthProviderRegistration:
    """§3.2 + §6 AUTH-02: does an ACTIVE registration permit this callback?

    Fail-closed throughout, and the failures are all one error to the caller
    (§11 `PROVIDER_NOT_ALLOWED`, "bez detalja konfiguracije"): telling an
    attacker *which* check rejected them is telling them what to change.

    This runs in addition to the adapter's own token validation, not instead of
    it. The adapter proves the token is genuine; the registry decides whether a
    genuine token from that issuer may be used here at all. An adapter someone
    configured but nobody registered fails here (§4.9), which is the difference
    between a fail-closed registry and a lookup table.
    """
    registration = active_registration(db, provider_key)
    if registration is None:
        raise ProviderNotAllowedError(PROVIDER_REFUSAL)

    # Exact match, no trimming and no case folding — see `registration_for_issuer`.
    if claims.issuer != registration.issuer:
        raise ProviderNotAllowedError(PROVIDER_REFUSAL)

    # An empty allowlist refuses everything. That is the intended reading: a
    # deployment that has not declared its client id has not declared it, and
    # "unconfigured" must not mean "anything".
    if claims.audience not in registration.allowed_audiences:
        raise ProviderNotAllowedError(PROVIDER_REFUSAL)

    if claims.algorithm is not None and claims.algorithm not in registration.allowed_algorithms:
        raise ProviderNotAllowedError(PROVIDER_REFUSAL)

    if redirect_uri is not None and redirect_uri not in registration.allowed_redirect_uris:
        raise ProviderNotAllowedError(PROVIDER_REFUSAL)

    return registration
