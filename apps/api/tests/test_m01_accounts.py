"""M01 §3.1–3.2: the account, its provider identities and the provider registry.

The thing these tests are really about is §2's one sentence: ``Person !=
UserAccount``. Everything else in M01 — revocation, suspension, linking — is
only meaningful once the row that signs in is a different row from the human the
school has a relationship with.

The sharpest invariants here are the two that say *no*:

* ``UNIQUE(provider_issuer, provider_subject)`` is global, so one external
  subject can never reach two accounts (§4.3). That is what makes M01-QA-007's
  two concurrent links resolve to exactly one winner instead of racing;
* a matching email links nothing (§4.5). Two providers asserting the same
  address are two identities, and the one test that would have passed under the
  old code — Google finding a password account by email — is the one that must
  now fail (M01-QA-012).
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import ForbiddenError
from app.config import get_settings
from app.domains.identity.accounts import (
    create_account_with_identity,
    find_identity,
    find_local_password_identity,
    link_identity,
    live_account_for_person,
    login_emails_for_person,
    person_for_identity,
)
from app.domains.identity.auth_enums import (
    GOOGLE_ISSUER,
    GOOGLE_PROVIDER,
    LOCAL_PASSWORD_ISSUER,
    LOCAL_PASSWORD_PROVIDER,
    AccountDisableReason,
    AuthProviderStatus,
    UserAccountStatus,
)
from app.domains.identity.auth_models import (
    AuthIdentity,
    AuthProviderRegistration,
    UserAccount,
)
from app.domains.identity.auth_providers import (
    active_registration,
    ensure_builtin_providers,
    registration_for_issuer,
    sync_provider_registry,
)
from app.platform import clock
from app.security.oidc import jit_provision
from app.security.password_auth import register_with_password
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import make_person

OTHER_ISSUER = "https://login.microsoftonline.com/common/v2.0"


def _account(db: Session, *, subject: str, email: str | None = None) -> UserAccount:
    person = make_person(db, given="A", family=subject[-4:])
    account, _ = create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
        login_email=email,
    )
    db.commit()
    return account


# ---------------------------------------------------------------------------
# §2 / §3.1 — the account is not the person
# ---------------------------------------------------------------------------


def test_account_and_first_identity_are_created_together(db: Session) -> None:
    """§4: an ACTIVE account always has a linked identity.

    The two rows are flushed in one call precisely so a failure later in the
    transaction takes both. An account that outlived its identity is one nobody
    can sign in to and nobody can see is broken (M01-QA-018).
    """
    account = _account(db, subject="sub-together", email="t@example.invalid")
    identities = db.execute(
        select(AuthIdentity).where(AuthIdentity.user_account_id == account.id)
    ).scalars().all()

    assert account.status is UserAccountStatus.ACTIVE
    assert account.authorization_version == 1
    assert len(identities) == 1
    assert identities[0].is_linked


def test_person_may_exist_with_no_account(db: Session) -> None:
    """§2: every child and many imported adults never sign in."""
    person = make_person(db, given="Dete", family="Bez")
    assert live_account_for_person(db, person.id) is None


def test_one_live_account_per_person(db: Session) -> None:
    """§2: at most one non-redundant active account."""
    account = _account(db, subject="sub-one")
    db.add(
        UserAccount(
            person_id=account.person_id,
            status=UserAccountStatus.ACTIVE,
            authorization_version=1,
            version=1,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_retired_account_does_not_block_a_new_one(db: Session) -> None:
    """The uniqueness is partial on purpose.

    §6 AUTH-11 keeps a disabled account's history rather than deleting it, so a
    permanent unique constraint would mean one disabled account bars that person
    from ever having another — a retention rule quietly doubling as a ban.
    """
    account = _account(db, subject="sub-retire")
    account.status = UserAccountStatus.DISABLED
    account.disabled_at = clock.now()
    account.disabled_reason_code = AccountDisableReason.SECURITY_INCIDENT
    db.commit()

    replacement, _ = create_account_with_identity(
        db,
        person_id=account.person_id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject="sub-retire-2",
    )
    db.commit()
    assert live_account_for_person(db, account.person_id).id == replacement.id


@pytest.mark.parametrize(
    "status, disabled_at, reason",
    [
        # A disabled account with no record of when or why.
        (UserAccountStatus.DISABLED, None, None),
        # A live account carrying a disable stamp.
        (UserAccountStatus.ACTIVE, "now", AccountDisableReason.LEGAL_REQUEST),
        # Half a disable: a time with no reason.
        (UserAccountStatus.DISABLED, "now", None),
    ],
)
def test_disable_stamp_and_status_must_agree(
    db: Session, status: UserAccountStatus, disabled_at: str | None, reason: object
) -> None:
    """§3.1: `disabled_at` and `disabled_reason_code` travel together, and only
    on an account that is actually disabled. §11 keeps `ACCOUNT_INACTIVE`
    generic to the user, so the audit trail is the only place the reason
    survives — a half-written one loses it."""
    person = make_person(db, given="Ck", family="Pair")
    db.add(
        UserAccount(
            person_id=person.id,
            status=status,
            authorization_version=1,
            version=1,
            disabled_at=clock.now() if disabled_at else None,
            disabled_reason_code=reason,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_authorization_version_must_be_positive(db: Session) -> None:
    """§3.1. Zero would make "bumped since issue" ambiguous at the one moment
    §4.7 needs it to be decisive."""
    person = make_person(db, given="Ck", family="Ver")
    db.add(UserAccount(person_id=person.id, authorization_version=0, version=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_user_account_carries_no_forbidden_column(db: Session) -> None:
    """§3.1's forbidden list, asserted against the mapped table rather than the
    source, so a column added through a mixin or a migration is caught too."""
    columns = {c.name for c in inspect(UserAccount).columns}
    forbidden = {
        "password",
        "password_hash",
        "session_secret",
        "refresh_token",
        "access_token",
        "id_token",
        "school_id",
        "tenant_id",
        "role",
        "role_code",
    }
    assert columns & forbidden == set()


# ---------------------------------------------------------------------------
# §3.2 / §4.3 — one subject, one account
# ---------------------------------------------------------------------------


def test_subject_is_globally_unique(db: Session) -> None:
    """M01-QA-007: two accounts cannot claim the same issuer+subject.

    Global, not per-account: the database is what decides the winner, so two
    genuinely concurrent links produce one success and one failure rather than
    two owners of one external identity.
    """
    first = _account(db, subject="shared-subject")
    second = _account(db, subject="other-subject")

    with pytest.raises(IntegrityError):
        link_identity(
            db,
            account=second,
            provider_key=GOOGLE_PROVIDER,
            issuer=GOOGLE_ISSUER,
            subject="shared-subject",
        )
    db.rollback()
    assert find_identity(db, GOOGLE_ISSUER, "shared-subject").user_account_id == first.id


def test_same_subject_under_two_issuers_does_not_collide(db: Session) -> None:
    """M01-QA-019: the subject is only meaningful under its issuer.

    Providers mint subjects in their own namespaces, and `sub=1234` at two
    identity providers is two people far more often than it is one.
    """
    account = _account(db, subject="1234")
    db.add(
        AuthProviderRegistration(
            provider_key="entra",
            issuer=OTHER_ISSUER,
            allowed_audiences=[],
            allowed_redirect_uris=[],
            allowed_algorithms=["RS256"],
            status=AuthProviderStatus.ACTIVE,
            config_revision=1,
        )
    )
    db.flush()
    link_identity(
        db,
        account=account,
        provider_key="entra",
        issuer=OTHER_ISSUER,
        subject="1234",
    )
    db.commit()

    assert find_identity(db, GOOGLE_ISSUER, "1234") is not None
    assert find_identity(db, OTHER_ISSUER, "1234") is not None


def test_subject_is_opaque_and_case_sensitive(db: Session) -> None:
    """§3.2: a subject is not trimmed, case-folded or normalized.

    A provider is entitled to issue subjects differing only in case, and a
    normalization here would hand one person's account to another.
    """
    _account(db, subject="CaseSensitive")
    assert find_identity(db, GOOGLE_ISSUER, "casesensitive") is None
    assert find_identity(db, GOOGLE_ISSUER, "CaseSensitive") is not None


def test_issuer_must_match_exactly(db: Session) -> None:
    """§3.2: no trailing-slash or case tolerance on the issuer either.

    Every tolerance is a second spelling, and an attacker who controls one
    spelling controls which registration applies (`PROVIDER_NOT_ALLOWED`).
    """
    assert registration_for_issuer(db, GOOGLE_ISSUER) is not None
    assert registration_for_issuer(db, GOOGLE_ISSUER + "/") is None
    assert registration_for_issuer(db, GOOGLE_ISSUER.upper()) is None


def test_unlink_time_and_reason_travel_together(db: Session) -> None:
    """§3.2, and §5: an unlink is a recorded decision, never a cleared column."""
    _account(db, subject="sub-unlink")
    identity = find_identity(db, GOOGLE_ISSUER, "sub-unlink")
    identity.unlinked_at = clock.now()
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# §4.5 — an email links nothing
# ---------------------------------------------------------------------------


def test_google_login_does_not_adopt_a_password_account_by_email(db: Session) -> None:
    """M01-QA-012, and the behaviour change this slice makes.

    The old code looked the address up and attached the Google subject to
    whatever account it found. That is account takeover for anyone who can get a
    provider to assert an address: §4.5 answers it flatly — "email podudaranje
    samo po sebi nikada ne linkuje nalog niti spaja osobe".
    """
    local = register_with_password(db, "ista@example.invalid", "dovoljnodugo1", "Ista", "Osoba")
    via_google = jit_provision(
        db, {"sub": "google-ista", "email": "ista@example.invalid", "name": "Ista Osoba"}
    )

    assert via_google.id != local.id
    assert find_local_password_identity(db, "ista@example.invalid").user_account_id != (
        find_identity(db, GOOGLE_ISSUER, "google-ista").user_account_id
    )


def test_two_oidc_identities_may_share_an_address(db: Session) -> None:
    """The corollary: the shared address must be *storable*, or the ban above
    would be enforced by a constraint that also breaks honest cases."""
    _account(db, subject="sub-share-1", email="deljena@example.invalid")
    _account(db, subject="sub-share-2", email="deljena@example.invalid")
    rows = db.execute(
        select(AuthIdentity).where(AuthIdentity.login_email == "deljena@example.invalid")
    ).scalars().all()
    assert len(rows) == 2


def test_one_local_password_identity_per_address(db: Session) -> None:
    """But the local adapter looks accounts up *by* the address, so two would be
    indistinguishable at sign-in."""
    register_with_password(db, "jedan@example.invalid", "dovoljnodugo1", "J", "P")
    identity = find_local_password_identity(db, "jedan@example.invalid")
    db.add(
        AuthIdentity(
            user_account_id=identity.user_account_id,
            provider_key=LOCAL_PASSWORD_PROVIDER,
            provider_issuer=LOCAL_PASSWORD_ISSUER,
            provider_subject="local:duplicate",
            login_email="jedan@example.invalid",
            linked_at=clock.now(),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_local_password_identity_requires_an_address(db: Session) -> None:
    """§3.2 again, from the other side: a local identity with no address could
    never be reached, and the adapter would need a branch for a row that cannot
    sign in."""
    account = _account(db, subject="sub-nolocalmail")
    db.add(
        AuthIdentity(
            user_account_id=account.id,
            provider_key=LOCAL_PASSWORD_PROVIDER,
            provider_issuer=LOCAL_PASSWORD_ISSUER,
            provider_subject="local:no-email",
            linked_at=clock.now(),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_login_emails_refuse_but_never_admit(db: Session) -> None:
    """The one sanctioned use of a login address (§23 invite acceptance): it
    decides "this invitation is for someone else", which grants nothing."""
    account = _account(db, subject="sub-emails", email="Poziv@Example.invalid")
    assert login_emails_for_person(db, account.person_id) == {"poziv@example.invalid"}


def test_unlinked_identity_drops_out_of_login_emails(db: Session) -> None:
    account = _account(db, subject="sub-gone", email="stara@example.invalid")
    identity = find_identity(db, GOOGLE_ISSUER, "sub-gone")
    identity.unlinked_at = clock.now()
    identity.unlink_reason_code = "ACCOUNT_HOLDER_REQUEST"
    db.commit()
    assert login_emails_for_person(db, account.person_id) == set()


# ---------------------------------------------------------------------------
# §3.1 — only ACTIVE signs in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status", [UserAccountStatus.SUSPENDED, UserAccountStatus.DISABLED]
)
def test_only_active_accounts_resolve_to_a_person(
    db: Session, status: UserAccountStatus
) -> None:
    """§3.1: "Samo `ACTIVE` može kreirati ili obnoviti aplikacionu sesiju."

    Suspended included — it is reversible by `AUTH-10`, not by simply waiting,
    and treating it as a softer state is how a suspension becomes advisory.
    """
    account = _account(db, subject=f"sub-{status.value.lower()}")
    account.status = status
    if status is UserAccountStatus.DISABLED:
        account.disabled_at = clock.now()
        account.disabled_reason_code = AccountDisableReason.SECURITY_INCIDENT
    db.commit()

    identity = find_identity(db, GOOGLE_ISSUER, f"sub-{status.value.lower()}")
    assert person_for_identity(db, identity) is None


def test_google_login_on_an_inactive_account_is_refused_generically(db: Session) -> None:
    """§6 AUTH-02 / §11: a known subject on an unusable account says no more
    than an unknown one does."""
    person = jit_provision(db, {"sub": "g-inactive", "email": "i@example.invalid", "name": "I A"})
    account = live_account_for_person(db, person.id)
    account.status = UserAccountStatus.SUSPENDED
    db.commit()

    with pytest.raises(ForbiddenError):
        jit_provision(db, {"sub": "g-inactive", "email": "i@example.invalid", "name": "I A"})


def test_successful_login_is_recorded_on_both_rows(db: Session) -> None:
    """§3.1 `last_authenticated_at`, §3.2 `last_verified_at`. Separate because
    they answer different questions: when did this human last get in, and when
    did this provider last vouch for them."""
    person = jit_provision(db, {"sub": "g-stamp", "email": "s@example.invalid", "name": "S T"})
    account = live_account_for_person(db, person.id)
    first = account.last_authenticated_at
    assert first is not None

    identity = find_identity(db, GOOGLE_ISSUER, "g-stamp")
    identity.last_verified_at = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
    db.commit()

    jit_provision(db, {"sub": "g-stamp", "email": "s@example.invalid", "name": "S T"})
    db.refresh(identity)
    assert identity.last_verified_at.year != 2000


def test_email_verified_only_when_the_provider_says_so(db: Session) -> None:
    """§3.2: `email_verified_at` exists only for an explicit provider claim.

    Google asserting `email_verified: false` and the local adapter asserting
    nothing are the same thing here — an address we hold, not one we trust.
    """
    jit_provision(
        db,
        {
            "sub": "g-unverified",
            "email": "neproveren@example.invalid",
            "name": "N P",
            "email_verified": False,
        },
    )
    assert find_identity(db, GOOGLE_ISSUER, "g-unverified").email_verified_at is None

    jit_provision(
        db,
        {
            "sub": "g-verified",
            "email": "proveren@example.invalid",
            "name": "P P",
            "email_verified": True,
        },
    )
    assert find_identity(db, GOOGLE_ISSUER, "g-verified").email_verified_at is not None


# ---------------------------------------------------------------------------
# §3.2 — the fail-closed registry
# ---------------------------------------------------------------------------


def test_an_identity_needs_a_registered_provider(db: Session) -> None:
    """Fail-closed by foreign key: an adapter with no registration is not a
    provider, whatever the deployment config says (§4.9)."""
    account = _account(db, subject="sub-unregistered")
    db.add(
        AuthIdentity(
            user_account_id=account.id,
            provider_key="facebook",
            provider_issuer="https://www.facebook.com",
            provider_subject="fb-1",
            linked_at=clock.now(),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_builtin_providers_are_seeded_and_idempotent(db: Session) -> None:
    ensure_builtin_providers(db)
    db.commit()
    keys = set(
        db.execute(select(AuthProviderRegistration.provider_key)).scalars().all()
    )
    assert {GOOGLE_PROVIDER, LOCAL_PASSWORD_PROVIDER} <= keys


def test_seeding_never_re_enables_a_disabled_provider(db: Session) -> None:
    """An operator turning a provider off is an audited config decision (§3.2).
    A restart that undid it would make the registry a copy of the deployment
    rather than a control over it."""
    google = db.get(AuthProviderRegistration, GOOGLE_PROVIDER)
    google.status = AuthProviderStatus.DISABLED
    db.commit()

    ensure_builtin_providers(db)
    db.commit()
    db.refresh(google)
    assert google.status is AuthProviderStatus.DISABLED
    assert active_registration(db, GOOGLE_PROVIDER) is None


def test_two_active_registrations_cannot_share_an_issuer(db: Session) -> None:
    """§3.2 requires *the* active registration for a callback's issuer. Two
    would make "exactly" undecidable at the moment it matters most."""
    db.add(
        AuthProviderRegistration(
            provider_key="google-copy",
            issuer=GOOGLE_ISSUER,
            allowed_audiences=[],
            allowed_redirect_uris=[],
            allowed_algorithms=["RS256"],
            status=AuthProviderStatus.ACTIVE,
            config_revision=1,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_registration_needs_at_least_one_algorithm(db: Session) -> None:
    """An empty algorithm list reads as "no policy", and the next reader will
    treat "no policy" as "any algorithm"."""
    db.add(
        AuthProviderRegistration(
            provider_key="no-alg",
            issuer="https://example.invalid/no-alg",
            allowed_audiences=[],
            allowed_redirect_uris=[],
            allowed_algorithms=[],
            status=AuthProviderStatus.ACTIVE,
            config_revision=1,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_registry_holds_no_client_secret(db: Session) -> None:
    """§3.2: secrets stay in the secret store. This table is business data — it
    is backed up, restored into staging, and read by anything with a session."""
    columns = {c.name for c in inspect(AuthProviderRegistration).columns}
    assert not any("secret" in name for name in columns)


def test_sync_reconciles_deployment_allowlists_without_changing_status(
    db: Session,
) -> None:
    """Audiences and redirects are deployment facts; status is an operator's.

    They are reconciled from settings so that a misconfigured deployment shows
    up at boot rather than at somebody's first sign-in attempt.
    """
    google = db.get(AuthProviderRegistration, GOOGLE_PROVIDER)
    google.status = AuthProviderStatus.DISABLED
    revision_before = google.config_revision
    db.commit()

    sync_provider_registry(db, get_settings())
    db.refresh(google)

    # Tests pin Google credentials off, so there is nothing to allow — and an
    # empty allowlist is the fail-closed answer, not a missing one.
    assert list(google.allowed_audiences) == []
    assert google.status is AuthProviderStatus.DISABLED
    assert google.config_revision == revision_before


def test_provider_registrations_survive_a_login(db: Session) -> None:
    """A sanity check on the FK direction: identities point at the registry, so
    the registry outlives them and a provider cannot be deleted out from under a
    linked account."""
    _account(db, subject="sub-fk")
    with pytest.raises(IntegrityError):
        db.execute(
            text("DELETE FROM auth_provider_registration WHERE provider_key = 'google'")
        )
    db.rollback()
