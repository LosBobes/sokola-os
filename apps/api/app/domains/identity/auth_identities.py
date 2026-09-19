"""M01 §6 AUTH-06/07: linking and unlinking a way to sign in.

These two commands change *how the account is reached*, which makes them more
dangerous than most things a user can do. Adding an identity is adding a key to
the house; removing one can be locking yourself out. §6 guards both with a fresh
re-authentication, and §7 is emphatic about what may never stand in for that
proof: a matching email, phone, name, date of birth, referral token or
invitation URL links nothing.

So both functions take a session that has *already* been proven fresh, and both
refuse to guess. They do not look anyone up by address, and they do not decide
that a subject is deserved — the caller has to have proven control of it, which
for a provider means completing a callback for that subject.

`AUTH-06` has no self-service HTTP surface, per §6: it is a service port for M02
and a future confirmed account-security flow. `AUTH-07` has none yet either,
because §14's `UI-AUTH-04` security screen does not exist and a command that
can lock a person out should arrive with the screen that explains it.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.errors import (
    IdentityAlreadyLinkedError,
    InvalidAccountTransitionError,
    LastIdentityProtectedError,
    ReauthenticationRequiredError,
    StaleVersionError,
)
from app.domains.identity import accounts, sessions
from app.domains.identity.auth_enums import (
    AuthEventOutcome,
    AuthEventType,
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

#: §6's fallback when no deployment value is confirmed. Deliberately short: this
#: is the window in which a borrowed, unlocked laptop can be used to add a
#: second way into someone's account, after which every login looks legitimate.
DEFAULT_STEP_UP_MAX_AGE = dt.timedelta(minutes=5)


def require_fresh_authentication(
    session: AuthSession,
    *,
    max_age: dt.timedelta = DEFAULT_STEP_UP_MAX_AGE,
    now: dt.datetime | None = None,
) -> None:
    """§6 AUTH-06/07: the provider must have authenticated this person recently.

    Measured from ``auth_time`` — when the *provider* proved it — and not from
    when we issued the session or last saw it. A session refreshed by ordinary
    use would otherwise look freshly proven forever, which is precisely the
    property that makes an unattended browser dangerous.

    Raises :class:`ReauthenticationRequiredError` rather than
    ``UNAUTHENTICATED``: the session is valid, just not recent, and a client
    that can tell the difference can re-authenticate instead of logging out.
    """
    moment = now or clock.now()
    if moment - session.auth_time > max_age:
        raise ReauthenticationRequiredError(
            "Potrebna je ponovna prijava da biste promenili način prijavljivanja."
        )


def link_identity(
    db: Session,
    *,
    account: UserAccount,
    acting_session: AuthSession,
    provider_key: str,
    issuer: str,
    subject: str,
    login_email: str | None = None,
    email_verified: bool = False,
    max_age: dt.timedelta = DEFAULT_STEP_UP_MAX_AGE,
    now: dt.datetime | None = None,
) -> AuthIdentity:
    """§6 AUTH-06. Attach a second, proven provider subject to a live account.

    The caller must already have proven control of ``subject`` — completing a
    provider callback for it is what that means. This function writes the link
    and enforces the guards; it does not decide the link was earned, because a
    function that both proves and records is one nobody can audit.

    One subject reaches one account (§4.3), so a subject already linked
    elsewhere is `IDENTITY_ALREADY_LINKED` and the other account is never named.
    A subject already linked *here* is returned as-is: repeating a successful
    link is not an error, and raising would make an interrupted flow
    unrecoverable.

    On success the authorization version moves and every other session is
    revoked. Adding a way into an account is a security event for every session
    that was open when it happened — except the one that just proved itself.
    """
    moment = now or clock.now()
    if account.status is not UserAccountStatus.ACTIVE:
        raise InvalidAccountTransitionError("Nalog nije aktivan.")
    require_fresh_authentication(acting_session, max_age=max_age, now=moment)

    sessions.lock_account(db, account.id)
    existing = accounts.find_identity(db, issuer, subject)
    if existing is not None:
        if existing.user_account_id != account.id or existing.unlinked_at is not None:
            # §11: the caller learns the subject is taken and nothing about who
            # has it. "Which account owns this address" is exactly the question
            # an attacker would like answered, and an unlinked row is still a
            # decision somebody made (§7) rather than a free subject.
            raise IdentityAlreadyLinkedError(
                "Ovaj način prijave je već povezan sa nalogom."
            )
        return existing

    identity = accounts.link_identity(
        db,
        account=account,
        provider_key=provider_key,
        issuer=issuer,
        subject=subject,
        login_email=login_email,
        email_verified=email_verified,
        now=moment,
    )
    sessions.revoke_account_sessions(
        db,
        account,
        reason=SessionRevokeReason.IDENTITY_LINKED,
        keep_session_id=acting_session.id,
        lock=False,
        now=moment,
    )
    return identity


def unlink_identity(
    db: Session,
    *,
    account: UserAccount,
    acting_session: AuthSession,
    identity: AuthIdentity,
    expected_version: int,
    reason_code: IdentityUnlinkReason,
    max_age: dt.timedelta = DEFAULT_STEP_UP_MAX_AGE,
    now: dt.datetime | None = None,
) -> AuthIdentity:
    """§6 AUTH-07. Remove one way in, never the last one.

    §2 requires every ACTIVE or SUSPENDED account to keep a linked identity, so
    removing the last is `LAST_IDENTITY_PROTECTED`. That is not a nicety: an
    account-security screen that could do it would lock someone out of their own
    account in one click, and nothing in M01 could let them back in.

    Unlinking the identity that is *currently proving* the request is refused
    too, unless another linked identity remains to vouch for the account — §6
    says "identitet kojim se trenutno potvrđuje radnja ako nema drugi dokaz".

    The row is unlinked, never deleted (§7: "Nema fizičkog brisanja istorije").
    A subject that was once ours stays recorded, so a later attempt to link it
    elsewhere is a decision somebody makes rather than a silent re-link.
    """
    moment = now or clock.now()
    if account.status is not UserAccountStatus.ACTIVE:
        # §6: not while the account is suspended or disabled. Those states are
        # already under an administrator's control, and letting the holder
        # change the sign-in method underneath that would take it back.
        raise InvalidAccountTransitionError("Nalog nije aktivan.")
    require_fresh_authentication(acting_session, max_age=max_age, now=moment)

    sessions.lock_account(db, account.id)
    db.refresh(account)
    if account.version != expected_version:
        raise StaleVersionError("Osvežite bezbednosno stanje i pokušajte ponovo.")

    if identity.user_account_id != account.id or identity.unlinked_at is not None:
        # Never confirm that an identity exists on some other account.
        raise LastIdentityProtectedError("Ovaj način prijave nije dostupan.")
    if _linked_count(db, account.id) <= 1:
        raise LastIdentityProtectedError(
            "Ne možete ukloniti poslednji način prijave."
        )

    identity.unlinked_at = moment
    identity.unlink_reason_code = reason_code

    # The acting session is kept only when some *other* identity still vouches
    # for this account. If the session being kept is the one whose identity just
    # went away, keeping it would be keeping a session nothing stands behind.
    keep = (
        acting_session.id
        if acting_session.auth_identity_id != identity.id
        else None
    )
    sessions.revoke_account_sessions(
        db,
        account,
        reason=SessionRevokeReason.IDENTITY_UNLINKED,
        keep_session_id=keep,
        lock=False,
        now=moment,
    )
    db.add(
        AuthenticationEvent(
            event_type=AuthEventType.IDENTITY_UNLINKED,
            outcome=AuthEventOutcome.SUCCEEDED,
            user_account_id=account.id,
            auth_identity_id=identity.id,
            provider_key=identity.provider_key,
            reason_code=reason_code.value,
            authorization_version=account.authorization_version,
            occurred_at=moment,
        )
    )
    return identity


def linked_identities(db: Session, account_id: str) -> list[AuthIdentity]:
    """The ways this account can currently be reached (§6 AUTH-Q01, §14)."""
    return list(
        db.execute(
            select(AuthIdentity)
            .where(
                AuthIdentity.user_account_id == account_id,
                AuthIdentity.unlinked_at.is_(None),
            )
            .order_by(AuthIdentity.linked_at)
        )
        .scalars()
        .all()
    )


def _linked_count(db: Session, account_id: str) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(AuthIdentity)
            .where(
                AuthIdentity.user_account_id == account_id,
                AuthIdentity.unlinked_at.is_(None),
            )
        ).scalar_one()
    )
