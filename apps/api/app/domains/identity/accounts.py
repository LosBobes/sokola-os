"""M01 §3.1–3.2: creating and reading accounts and their provider identities.

Everything here holds one rule: an ``ACTIVE`` or ``SUSPENDED`` account always
has at least one linked identity (§2). So an account is never created on its
own — ``create_account_with_identity`` makes both in one flush, which is §4's
"atomarno nastajanje naloga i prvog identiteta" and what stops M01-QA-018's
half-finished activation from leaving an account nobody can sign in to.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.identity.auth_enums import (
    LIVE_ACCOUNT_STATUSES,
    LOCAL_PASSWORD_PROVIDER,
    AuthEventOutcome,
    AuthEventType,
    UserAccountStatus,
)
from app.domains.identity.auth_models import (
    AuthenticationEvent,
    AuthIdentity,
    UserAccount,
)
from app.domains.identity.models import Person
from app.platform import clock


def normalize_email(email: str) -> str:
    """Lowercase and trim, for *lookup* only.

    Never applied to ``provider_subject``: §3.2 says a subject is opaque and
    keeps its case. An email is a label we choose how to index; a subject is a
    value the provider chose and we are not entitled to reinterpret.
    """
    return email.strip().lower()


def live_account_for_person(db: Session, person_id: str) -> UserAccount | None:
    """The person's one account that can authenticate, or be returned to it."""
    stmt = select(UserAccount).where(
        UserAccount.person_id == person_id,
        UserAccount.status.in_(LIVE_ACCOUNT_STATUSES),
    )
    return db.execute(stmt).scalar_one_or_none()


def find_identity(db: Session, issuer: str, subject: str) -> AuthIdentity | None:
    """The identity for this exact provider subject, linked or not.

    An unlinked row is still returned: §7 wants a deliberate, audited decision
    about a subject that was once ours, not a silent re-link on next sign-in.
    """
    stmt = select(AuthIdentity).where(
        AuthIdentity.provider_issuer == issuer,
        AuthIdentity.provider_subject == subject,
    )
    return db.execute(stmt).scalar_one_or_none()


def find_local_password_identity(db: Session, email: str) -> AuthIdentity | None:
    """The local adapter's lookup: the address someone typed into the form.

    This is not email-based linking (§4.5). The address *is* this provider's
    login handle, the way a subject is Google's; what §4.5 forbids is letting a
    matching address carry an identity from one provider over to another.
    """
    stmt = select(AuthIdentity).where(
        AuthIdentity.provider_key == LOCAL_PASSWORD_PROVIDER,
        AuthIdentity.unlinked_at.is_(None),
        func.lower(AuthIdentity.login_email) == normalize_email(email),
    )
    return db.execute(stmt).scalar_one_or_none()


def person_for_identity(db: Session, identity: AuthIdentity) -> Person | None:
    """The person behind a linked identity, if the account can still sign in.

    Returns ``None`` for a suspended, disabled or retired account — §3.1 lets
    only ``ACTIVE`` open a session, and the caller must answer it the same way
    it answers an unknown subject (§11: ``ACCOUNT_INACTIVE`` is generic).
    """
    if identity.unlinked_at is not None:
        return None
    account = db.get(UserAccount, identity.user_account_id)
    if account is None or account.status is not UserAccountStatus.ACTIVE:
        return None
    return db.get(Person, account.person_id)


def create_account_with_identity(
    db: Session,
    *,
    person_id: str,
    provider_key: str,
    issuer: str,
    subject: str,
    login_email: str | None = None,
    email_verified: bool = False,
    now: dt.datetime | None = None,
) -> tuple[UserAccount, AuthIdentity]:
    """§4: the account and its first identity, or neither.

    Both rows are flushed together so a failure anywhere after this point rolls
    back an account that has no way in, rather than leaving one behind for a
    later sign-in to adopt.
    """
    moment = now or clock.now()
    account = UserAccount(
        person_id=person_id,
        status=UserAccountStatus.ACTIVE,
        authorization_version=1,
        last_authenticated_at=moment,
    )
    db.add(account)
    db.flush()
    identity = link_identity(
        db,
        account=account,
        provider_key=provider_key,
        issuer=issuer,
        subject=subject,
        login_email=login_email,
        email_verified=email_verified,
        now=moment,
    )
    return account, identity


def link_identity(
    db: Session,
    *,
    account: UserAccount,
    provider_key: str,
    issuer: str,
    subject: str,
    login_email: str | None = None,
    email_verified: bool = False,
    now: dt.datetime | None = None,
) -> AuthIdentity:
    """Attach one provider subject to an existing account, with its audit event.

    The caller is responsible for having proven control of ``subject`` — this
    function writes the link, it does not decide that the link is earned
    (§6 AUTH-06). ``UNIQUE(provider_issuer, provider_subject)`` is what makes a
    concurrent second attempt fail rather than produce a second owner.
    """
    moment = now or clock.now()
    event = AuthenticationEvent(
        event_type=AuthEventType.IDENTITY_LINKED,
        outcome=AuthEventOutcome.SUCCEEDED,
        user_account_id=account.id,
        provider_key=provider_key,
        occurred_at=moment,
    )
    db.add(event)
    db.flush()

    identity = AuthIdentity(
        user_account_id=account.id,
        provider_key=provider_key,
        provider_issuer=issuer,
        provider_subject=subject,
        login_email=normalize_email(login_email) if login_email else None,
        email_verified_at=moment if (email_verified and login_email) else None,
        linked_at=moment,
        last_verified_at=moment,
        created_by_event_id=event.id,
    )
    db.add(identity)
    db.flush()
    event.auth_identity_id = identity.id
    return identity


def record_authentication(
    db: Session, account: UserAccount, identity: AuthIdentity, *, now: dt.datetime | None = None
) -> None:
    """Note a successful sign-in on both rows and in the security log (§13)."""
    moment = now or clock.now()
    account.last_authenticated_at = moment
    identity.last_verified_at = moment
    db.add(
        AuthenticationEvent(
            event_type=AuthEventType.LOGIN_SUCCEEDED,
            outcome=AuthEventOutcome.SUCCEEDED,
            user_account_id=account.id,
            auth_identity_id=identity.id,
            provider_key=identity.provider_key,
            authorization_version=account.authorization_version,
            occurred_at=moment,
        )
    )


def record_failed_login(
    db: Session,
    *,
    provider_key: str,
    reason_code: str,
    user_account_id: str | None = None,
    now: dt.datetime | None = None,
) -> None:
    """§13's ``auth.login_failed``.

    ``user_account_id`` stays ``None`` when the attempt never resolved to an
    account. Filling it in from a guessed email would put the enumeration
    oracle §11 keeps out of the response body into the audit trail instead.
    """
    db.add(
        AuthenticationEvent(
            event_type=AuthEventType.LOGIN_FAILED,
            outcome=AuthEventOutcome.FAILED,
            user_account_id=user_account_id,
            provider_key=provider_key,
            reason_code=reason_code,
            occurred_at=now or clock.now(),
        )
    )


def login_emails_for_person(db: Session, person_id: str) -> set[str]:
    """Every address this person's linked identities sign in with.

    Used to *refuse* a mismatched invitation, never to admit one: §4.5's ban is
    on an email granting access, and a refusal on one grants nothing.
    """
    stmt = (
        select(AuthIdentity.login_email)
        .join(UserAccount, UserAccount.id == AuthIdentity.user_account_id)
        .where(
            UserAccount.person_id == person_id,
            AuthIdentity.unlinked_at.is_(None),
            AuthIdentity.login_email.is_not(None),
        )
    )
    return {normalize_email(v) for v in db.execute(stmt).scalars().all() if v}
