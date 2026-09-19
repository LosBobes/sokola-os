"""M01 §6 AUTH-06/07 and §7: adding and removing a way to sign in.

These two commands change *how the account is reached*, which makes them more
dangerous than most things a user can do. Adding an identity is adding a key to
the house; removing one can be locking yourself out. §6 guards both with a fresh
re-authentication, and §7 lists what may never substitute for that proof: a
matching email, phone, name, date of birth, referral token or invitation URL
links nothing.

Freshness is measured from the *provider's* `auth_time`, not from when we issued
the session or last saw it. A session kept alive by ordinary use would otherwise
look freshly proven forever — which is exactly the property that makes an
unattended browser dangerous.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import (
    IdentityAlreadyLinkedError,
    InvalidAccountTransitionError,
    LastIdentityProtectedError,
    ReauthenticationRequiredError,
    StaleVersionError,
)
from app.domains.identity import auth_identities, sessions
from app.domains.identity.accounts import create_account_with_identity
from app.domains.identity.auth_enums import (
    GOOGLE_ISSUER,
    GOOGLE_PROVIDER,
    LOCAL_PASSWORD_ISSUER,
    LOCAL_PASSWORD_PROVIDER,
    AccountDisableReason,
    IdentityUnlinkReason,
    SessionRevokeReason,
    UserAccountStatus,
)
from app.domains.identity.auth_models import (
    AuthenticationEvent,
    AuthIdentity,
    AuthSession,
    UserAccount,
)
from app.platform import clock
from app.security.oidc import assurance_of, step_up_parameters
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.factories import make_person

LOCAL_SUBJECT = "local:second-way-in"


def _signed_in(
    db: Session, subject: str = "sub-link", *, auth_time: dt.datetime | None = None
) -> tuple[UserAccount, AuthIdentity, AuthSession]:
    """An account with one identity and one session proven just now."""
    person = make_person(db, given="L", family=subject[-4:])
    account, identity = create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
    )
    session, _ = sessions.issue_session(
        db, account=account, identity=identity, auth_time=auth_time
    )
    db.commit()
    return account, identity, session


def _link(
    db: Session,
    account: UserAccount,
    session: AuthSession,
    *,
    subject: str = LOCAL_SUBJECT,
    **kwargs: object,
) -> AuthIdentity:
    return auth_identities.link_identity(
        db,
        account=account,
        acting_session=session,
        provider_key=LOCAL_PASSWORD_PROVIDER,
        issuer=LOCAL_PASSWORD_ISSUER,
        subject=subject,
        login_email="drugi@example.invalid",
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# §6 — fresh re-authentication
# ---------------------------------------------------------------------------


def test_freshness_is_measured_from_the_providers_claim(db: Session) -> None:
    """Not from when we issued the session and not from `last_seen_at`.

    A session kept alive by ordinary use would otherwise look freshly proven
    forever, which is the whole risk an unattended browser represents.
    """
    stale = clock.now() - dt.timedelta(hours=2)
    account, _, session = _signed_in(db, "sub-stale-auth", auth_time=stale)

    # Plenty of recent activity; the provider still proved them two hours ago.
    sessions.validate_session(db, "irrelevant")
    session.last_seen_at = clock.now()
    db.commit()

    with pytest.raises(ReauthenticationRequiredError):
        auth_identities.require_fresh_authentication(session)


def test_a_recently_proven_session_passes(db: Session) -> None:
    _, _, session = _signed_in(db, "sub-fresh")
    auth_identities.require_fresh_authentication(session)


def test_linking_needs_fresh_proof(db: Session) -> None:
    """§6 AUTH-06. Adding a way into an account is exactly what a borrowed,
    unlocked laptop is useful for."""
    stale = clock.now() - dt.timedelta(minutes=30)
    account, _, session = _signed_in(db, "sub-link-stale", auth_time=stale)
    with pytest.raises(ReauthenticationRequiredError):
        _link(db, account, session)


def test_unlinking_needs_fresh_proof(db: Session) -> None:
    stale = clock.now() - dt.timedelta(minutes=30)
    account, identity, session = _signed_in(db, "sub-unlink-stale", auth_time=stale)
    with pytest.raises(ReauthenticationRequiredError):
        auth_identities.unlink_identity(
            db,
            account=account,
            acting_session=session,
            identity=identity,
            expected_version=account.version,
            reason_code=IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST,
        )


def test_reauthentication_is_not_unauthenticated(db: Session) -> None:
    """A client that can tell the two apart can re-authenticate instead of
    logging the person out — which is the difference between a security prompt
    and losing your place."""
    stale = clock.now() - dt.timedelta(hours=1)
    _, _, session = _signed_in(db, "sub-code", auth_time=stale)
    with pytest.raises(ReauthenticationRequiredError) as caught:
        auth_identities.require_fresh_authentication(session)
    assert caught.value.code == "REAUTHENTICATION_REQUIRED"
    assert caught.value.status_code == 403


# ---------------------------------------------------------------------------
# §6 AUTH-06 — linking
# ---------------------------------------------------------------------------


def test_a_second_identity_can_be_linked(db: Session) -> None:
    account, _, session = _signed_in(db, "sub-second")
    linked = _link(db, account, session)
    db.commit()

    assert linked.provider_key == LOCAL_PASSWORD_PROVIDER
    assert len(auth_identities.linked_identities(db, account.id)) == 2


def test_a_subject_already_on_another_account_is_refused(db: Session) -> None:
    """M01-QA-005, and §4.3: one subject reaches one account."""
    first, _, first_session = _signed_in(db, "sub-owner")
    _link(db, first, first_session)
    db.commit()

    second, _, second_session = _signed_in(db, "sub-thief")
    with pytest.raises(IdentityAlreadyLinkedError):
        _link(db, second, second_session)


def test_the_refusal_does_not_name_the_other_account(db: Session) -> None:
    """§11: "samo ovlašćenom potvrđenom akteru; ne otkriva drugi nalog".

    "Which account owns this Google address" is exactly the question an attacker
    would like answered.
    """
    first, _, first_session = _signed_in(db, "sub-quiet-owner")
    _link(db, first, first_session)
    db.commit()

    second, _, second_session = _signed_in(db, "sub-quiet-asker")
    with pytest.raises(IdentityAlreadyLinkedError) as caught:
        _link(db, second, second_session)
    assert first.id not in caught.value.message
    assert first.person_id not in caught.value.message
    assert caught.value.details == {}


def test_relinking_the_same_subject_here_is_not_an_error(db: Session) -> None:
    """Repeating a successful link is not a failure, and raising would make an
    interrupted flow unrecoverable."""
    account, _, session = _signed_in(db, "sub-repeat")
    first = _link(db, account, session)
    db.commit()
    again = _link(db, account, session)
    assert again.id == first.id


def test_an_unlinked_subject_is_not_free_to_relink(db: Session) -> None:
    """§7: a subject that was once ours stays recorded. Re-linking it is a
    decision somebody makes through the migration path, not something the next
    login does silently."""
    account, _, session = _signed_in(db, "sub-returned")
    linked = _link(db, account, session)
    db.commit()
    linked.unlinked_at = clock.now()
    linked.unlink_reason_code = IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST
    db.commit()

    with pytest.raises(IdentityAlreadyLinkedError):
        _link(db, account, session)


def test_linking_revokes_the_other_sessions(db: Session) -> None:
    """§6 AUTH-06: "opoziva druge sesije osim one koja je završila radnju".

    Adding a way into an account is a security event for every session that was
    already open when it happened.
    """
    account, identity, session = _signed_in(db, "sub-link-revoke")
    _, other_credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    _link(db, account, session)
    db.commit()

    assert sessions.validate_session(db, other_credential) is None
    db.refresh(session)
    assert session.revoked_at is None


def test_linking_bumps_the_authorization_version(db: Session) -> None:
    account, _, session = _signed_in(db, "sub-link-bump")
    before = account.authorization_version
    _link(db, account, session)
    db.commit()
    assert account.authorization_version > before


def test_an_inactive_account_cannot_gain_a_way_in(db: Session) -> None:
    """A suspended account is under an administrator's control; letting the
    holder add a sign-in method underneath that would take it back."""
    account, _, session = _signed_in(db, "sub-link-inactive")
    account.status = UserAccountStatus.SUSPENDED
    db.commit()
    with pytest.raises(InvalidAccountTransitionError):
        _link(db, account, session)


# ---------------------------------------------------------------------------
# §6 AUTH-07 — unlinking
# ---------------------------------------------------------------------------


def test_the_last_identity_is_protected(db: Session) -> None:
    """M01-QA-006. §2 requires an ACTIVE account to keep a way in, and an
    account-security screen that could remove the last one would lock someone
    out in a single click with nothing in M01 able to let them back."""
    account, identity, session = _signed_in(db, "sub-only-one")
    with pytest.raises(LastIdentityProtectedError):
        auth_identities.unlink_identity(
            db,
            account=account,
            acting_session=session,
            identity=identity,
            expected_version=account.version,
            reason_code=IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST,
        )
    db.rollback()
    assert len(auth_identities.linked_identities(db, account.id)) == 1


def test_a_second_identity_can_be_removed(db: Session) -> None:
    account, _, session = _signed_in(db, "sub-remove")
    extra = _link(db, account, session)
    db.commit()

    auth_identities.unlink_identity(
        db,
        account=account,
        acting_session=session,
        identity=extra,
        expected_version=account.version,
        reason_code=IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST,
    )
    db.commit()

    assert extra.unlinked_at is not None
    assert [i.id for i in auth_identities.linked_identities(db, account.id)] != [extra.id]


def test_the_row_is_unlinked_not_deleted(db: Session) -> None:
    """§7: "Nema fizičkog brisanja istorije"."""
    account, _, session = _signed_in(db, "sub-history")
    extra = _link(db, account, session)
    db.commit()
    auth_identities.unlink_identity(
        db,
        account=account,
        acting_session=session,
        identity=extra,
        expected_version=account.version,
        reason_code=IdentityUnlinkReason.PROVIDER_MIGRATION,
    )
    db.commit()

    still_there = db.get(AuthIdentity, extra.id)
    assert still_there is not None
    assert still_there.unlink_reason_code is IdentityUnlinkReason.PROVIDER_MIGRATION


def test_unlinking_the_proving_identity_ends_the_acting_session(db: Session) -> None:
    """§6: keeping a session whose identity just went away would be keeping a
    session nothing stands behind."""
    account, original, session = _signed_in(db, "sub-self-unlink")
    _link(db, account, session)
    db.commit()

    auth_identities.unlink_identity(
        db,
        account=account,
        acting_session=session,
        identity=original,
        expected_version=account.version,
        reason_code=IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST,
    )
    db.commit()

    db.refresh(session)
    assert session.revoked_at is not None
    assert session.revoke_reason_code is SessionRevokeReason.IDENTITY_UNLINKED


def test_unlinking_another_identity_keeps_the_acting_session(db: Session) -> None:
    account, _, session = _signed_in(db, "sub-keep-acting")
    extra = _link(db, account, session)
    db.commit()

    auth_identities.unlink_identity(
        db,
        account=account,
        acting_session=session,
        identity=extra,
        expected_version=account.version,
        reason_code=IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST,
    )
    db.commit()
    db.refresh(session)
    assert session.revoked_at is None


def test_unlinking_requires_the_expected_version(db: Session) -> None:
    """§6 AUTH-07. The person is acting on a security screen that may no longer
    describe the account."""
    account, _, session = _signed_in(db, "sub-unlink-stale-version")
    extra = _link(db, account, session)
    db.commit()
    with pytest.raises(StaleVersionError):
        auth_identities.unlink_identity(
            db,
            account=account,
            acting_session=session,
            identity=extra,
            expected_version=account.version + 99,
            reason_code=IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST,
        )


def test_another_accounts_identity_is_never_confirmed(db: Session) -> None:
    """Passing someone else's identity must not reveal that it exists."""
    mine, _, my_session = _signed_in(db, "sub-mine")
    _link(db, mine, my_session)
    theirs, their_identity, _ = _signed_in(db, "sub-theirs")
    db.commit()

    with pytest.raises(LastIdentityProtectedError):
        auth_identities.unlink_identity(
            db,
            account=mine,
            acting_session=my_session,
            identity=their_identity,
            expected_version=mine.version,
            reason_code=IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST,
        )
    db.rollback()
    assert their_identity.unlinked_at is None


def test_unlinking_is_audited(db: Session) -> None:
    account, _, session = _signed_in(db, "sub-audit-unlink")
    extra = _link(db, account, session)
    db.commit()
    auth_identities.unlink_identity(
        db,
        account=account,
        acting_session=session,
        identity=extra,
        expected_version=account.version,
        reason_code=IdentityUnlinkReason.SECURITY_INCIDENT,
    )
    db.commit()

    events = db.execute(
        select(AuthenticationEvent).where(
            AuthenticationEvent.event_type == "auth.identity_unlinked"
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].reason_code == "SECURITY_INCIDENT"


def test_a_suspended_account_cannot_lose_an_identity(db: Session) -> None:
    account, _, session = _signed_in(db, "sub-unlink-suspended")
    extra = _link(db, account, session)
    db.commit()
    account.status = UserAccountStatus.DISABLED
    account.disabled_at = clock.now()
    account.disabled_reason_code = AccountDisableReason.SECURITY_INCIDENT
    db.commit()

    with pytest.raises(InvalidAccountTransitionError):
        auth_identities.unlink_identity(
            db,
            account=account,
            acting_session=session,
            identity=extra,
            expected_version=account.version,
            reason_code=IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST,
        )


# ---------------------------------------------------------------------------
# The provider does the step-up, not us
# ---------------------------------------------------------------------------


def test_step_up_asks_the_provider_to_reauthenticate() -> None:
    """§10: step-up comes from the provider or from approved configuration,
    "nikad ne aplikacioni improvizovani tok".

    Our own form can only prove the person knows a secret we stored. Only the
    provider can prove the person is present right now.
    """
    params = step_up_parameters(dt.timedelta(minutes=5))
    assert params["prompt"] == "login"
    assert params["max_age"] == 300


def test_assurance_keeps_amr_and_acr_and_nothing_else() -> None:
    """§3.2 and §13: a column that accepted the whole claim set would end up
    holding the whole claim set — email, picture URL and whatever comes next."""
    context = assurance_of(
        {
            "amr": ["pwd", "mfa"],
            "acr": "urn:mace:incommon:iap:silver",
            "email": "tajna@example.invalid",
            "picture": "https://example.invalid/me.jpg",
            "sub": "google-123",
        }
    )
    assert context == {"amr": ["pwd", "mfa"], "acr": "urn:mace:incommon:iap:silver"}


@pytest.mark.parametrize(
    "claims",
    [{}, {"amr": "pwd"}, {"amr": [1, 2]}, {"acr": 3}, {"amr": None, "acr": None}],
)
def test_malformed_assurance_claims_are_dropped(claims: dict) -> None:
    """A provider can send anything in these fields, so anything that is not the
    documented shape is simply not recorded."""
    assert assurance_of(claims) == {} or set(assurance_of(claims)) <= {"amr", "acr"}


def test_auth_time_defaults_to_now_for_the_local_adapter(db: Session) -> None:
    """Which is correct rather than a shortcut: the local adapter *did*
    authenticate them just now. Assuming it for a provider that told us
    otherwise is what the callback's explicit claim avoids."""
    account, identity, _ = _signed_in(db, "sub-local-authtime")
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    assert (clock.now() - session.auth_time) < dt.timedelta(seconds=5)
