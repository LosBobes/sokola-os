"""M01 §3.1–3.2: the account, its provider identities and the provider registry.

The shape of this file is §2's normative result, ``Person != UserAccount``. A
``Person`` is a human the school has a relationship with, and most of them —
every child, and many imported adults — never sign in at all. A ``UserAccount``
is the thing that signs in. Keeping them one row is what makes "deactivate the
login" and "remove the person from the roster" the same button, which is exactly
the conflation §1 exists to prevent.

Three further separations, each load-bearing:

* the **identity** is the account's link to one provider subject, not the
  account itself. ``UNIQUE(provider_issuer, provider_subject)`` is global, so
  one external subject can never reach two accounts (§4.3);
* the **registry** decides which issuers exist at all, fail-closed. An adapter
  that is configured but has no ``ACTIVE`` row here cannot complete a callback;
* the **credential** (for the local email+password adapter) lives in its own
  table. §3.1 forbids a password column on ``UserAccount``, and the point of
  that ban is not tidiness: an account row is read on every authorization
  decision, and a hash that rides along on every one of those reads is a hash
  that will eventually be logged.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id, new_random_id
from app.domains.identity.auth_enums import (
    AccountDisableReason,
    AuthEventOutcome,
    AuthEventType,
    AuthProviderStatus,
    IdentityUnlinkReason,
    SessionRevokeReason,
    UserAccountStatus,
)

_LIVE = "('ACTIVE', 'SUSPENDED')"


class UserAccount(Base, TimestampMixin):
    """§3.1. One SOKOLA sign-in account, bound to exactly one ``Person``.

    ``authorization_version`` is the security clock. §4.7 requires that bumping
    it invalidate every existing session for any request that *starts* after the
    commit — so it is read on the authorization path itself, not projected to it
    by an outbox consumer. The outbox event exists (§13) to shut realtime
    channels and secondary projections; it is never the proof.

    Forbidden here by §3.1, and checked by ``scripts/check_architecture.py``: a
    password or password hash, a raw provider token, a session secret, and any
    global tenant or role column. The last of those is the one that looks
    harmless — a ``school_id`` on the account would be a tenant claim carried by
    authentication, and §8 puts that decision on every individual request.
    """

    __tablename__ = "user_account"
    __table_args__ = (
        CheckConstraint("authorization_version > 0", name="ck_user_account_auth_version"),
        CheckConstraint("version > 0", name="ck_user_account_version"),
        # A reason without a timestamp (or the reverse) is a half-written
        # disable, and §11's `ACCOUNT_INACTIVE` would then have no audit behind
        # it.
        CheckConstraint(
            "(disabled_at IS NULL) = (disabled_reason_code IS NULL)",
            name="ck_user_account_disabled_pair",
        ),
        CheckConstraint(
            f"(status IN {_LIVE}) = (disabled_at IS NULL)",
            name="ck_user_account_disabled_status",
        ),
        # §2: at most one non-redundant active account per person. Partial,
        # because a disabled or merged-retired account must stay on the row for
        # the audit history (§6 AUTH-11: "bez brisanja audit istorije") without
        # blocking a later, deliberately re-created one.
        Index(
            "uq_user_account_live_person",
            "person_id",
            unique=True,
            postgresql_where=text(f"status IN {_LIVE}"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("uac"))
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[UserAccountStatus] = mapped_column(
        enum_type(UserAccountStatus), nullable=False, default=UserAccountStatus.ACTIVE
    )
    #: §3.1, a positive integer. Bumped by AUTH-05/06/07/08/09/10/11.
    authorization_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    last_authenticated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    disabled_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    disabled_reason_code: Mapped[AccountDisableReason | None] = mapped_column(
        enum_type(AccountDisableReason), nullable=True
    )
    #: Optimistic concurrency. Distinct from ``authorization_version`` on
    #: purpose: §6's administrative commands take an ``expected_version`` to
    #: refuse a stale write, while the authorization version is a revocation
    #: epoch that every reader compares against. Merging them would mean a
    #: harmless concurrent edit silently logs the account out.
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class AuthProviderRegistration(Base, TimestampMixin):
    """§3.2. The fail-closed registry of allowed providers.

    A callback's issuer must match an ``ACTIVE`` row here *exactly*. §3.2 is
    specific about what may not select an identity: an alias, a display name, a
    request parameter or an email domain. That is why ``issuer`` is compared
    byte for byte and why none of those things appear as columns — a field that
    exists is a field something will eventually match on (M01-QA-019).

    Client secrets are not here. They stay in the secret store / deploy config,
    because this table is business data: it is backed up, restored into staging,
    and read by anything holding a database session.
    """

    __tablename__ = "auth_provider_registration"
    __table_args__ = (
        # Two active registrations for one issuer would make "the active
        # registration" ambiguous at exactly the moment §3.2 requires an exact
        # match. Disabled rows are kept for the config history.
        Index(
            "uq_auth_provider_active_issuer",
            "issuer",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        CheckConstraint("config_revision > 0", name="ck_auth_provider_config_revision"),
        CheckConstraint(
            "cardinality(allowed_algorithms) > 0", name="ck_auth_provider_algorithms"
        ),
    )

    #: Natural key: the adapter names the provider it is, and a surrogate id
    #: here would let two rows claim the same adapter.
    provider_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: The exact canonical issuer from the approved provider metadata. Compared
    #: literally — a differing case or trailing path is a different issuer and
    #: is `PROVIDER_NOT_ALLOWED`.
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_audiences: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    allowed_redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    allowed_algorithms: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    #: OIDC discovery document, when the provider publishes one. NULL for the
    #: local password adapter, which has no keys to discover.
    discovery_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AuthProviderStatus] = mapped_column(
        enum_type(AuthProviderStatus), nullable=False, default=AuthProviderStatus.ACTIVE
    )
    #: Bumped on every audited config change, so an audit entry can name the
    #: revision it acted under.
    config_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AuthIdentity(Base, TimestampMixin):
    """§3.2. One verified link between an account and one provider subject.

    ``provider_subject`` is opaque: not trimmed, not case-folded, not normalized
    by any business rule. Providers are entitled to subjects that differ only in
    case, and a normalization here would quietly merge two people.

    ``login_email`` is the minimized display snapshot §3.2 permits, never an
    identity. §4.5 is absolute that a matching email links nothing on its own;
    the column exists so a sign-in screen can say which account it is about, and
    so an invitation can *refuse* a mismatched one. Refusing on an email is
    safe; admitting on one is not.
    """

    __tablename__ = "auth_identity"
    __table_args__ = (
        # §2, global and not per-account: one external subject reaches exactly
        # one account, which is what makes M01-QA-007's two concurrent links
        # resolve deterministically instead of racing.
        UniqueConstraint(
            "provider_issuer", "provider_subject", name="uq_auth_identity_subject"
        ),
        CheckConstraint(
            "(unlinked_at IS NULL) = (unlink_reason_code IS NULL)",
            name="ck_auth_identity_unlink_pair",
        ),
        CheckConstraint(
            "email_verified_at IS NULL OR login_email IS NOT NULL",
            name="ck_auth_identity_verified_needs_email",
        ),
        # The local adapter has no directory to look a subject up in: the
        # address the person types *is* the lookup. Without this the adapter
        # would need a fallback path for a row that cannot sign in at all.
        CheckConstraint(
            "provider_key <> 'local-password' OR login_email IS NOT NULL",
            name="ck_auth_identity_local_needs_email",
        ),
        # Replaces the legacy global `UNIQUE(type, value)` on email, but only
        # where an email really is the key. Two OIDC identities may assert the
        # same address (M01-QA-012 requires exactly that, and requires it not to
        # link them); two local passwords for one address could not be told
        # apart at sign-in.
        Index(
            "uq_auth_identity_local_email",
            text("lower(login_email)"),
            unique=True,
            postgresql_where=text(
                "provider_key = 'local-password' AND unlinked_at IS NULL"
            ),
        ),
        Index(
            "ix_auth_identity_account_live",
            "user_account_id",
            postgresql_where=text("unlinked_at IS NULL"),
        ),
        Index("ix_auth_identity_login_email", text("lower(login_email)")),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aid"))
    user_account_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), nullable=False
    )
    provider_key: Mapped[str] = mapped_column(
        ForeignKey("auth_provider_registration.provider_key", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_issuer: Mapped[str] = mapped_column(Text, nullable=False)
    provider_subject: Mapped[str] = mapped_column(Text, nullable=False)
    #: Set only when the provider explicitly asserts the address is verified.
    #: An unverified claim leaves this NULL and the address stays a label.
    email_verified_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    login_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    linked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unlinked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unlink_reason_code: Mapped[IdentityUnlinkReason | None] = mapped_column(
        enum_type(IdentityUnlinkReason), nullable=True
    )
    #: The `AuthenticationEvent` that created this link (§3.2). Nullable because
    #: identities carried over by the M01 migration predate the event log, and
    #: inventing an event for them would fabricate security history.
    created_by_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("authentication_event.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def is_linked(self) -> bool:
        return self.unlinked_at is None


class AuthSession(Base):
    """§3.2. One active sign-in, server-side, so it can be ended.

    The repo's previous session was a signed cookie holding a person id. A
    signed cookie is a *claim* the server re-verifies, never a record the server
    owns — so "log me out everywhere" had nothing to act on, and a cookie issued
    on a borrowed laptop stayed valid until its signature aged out. This table
    is the record.

    Two expiries, both enforced, §3.2's fail-closed defaults: 30 minutes idle
    and 12 hours absolute, whichever comes first. The idle one slides on use and
    is clamped to the absolute one, because an idle window that could push past
    the absolute deadline would make the absolute deadline advisory.

    ``authorization_version_at_issue`` is the whole of §4.7. Every protected
    request compares it against the account's current version, so a bump ends
    every session on the next request — without an outbox consumer, a cache
    invalidation, or any other thing that might not have run yet.

    What is *not* here: the credential. Only its digest is stored, so a database
    copy does not yield working sessions. And no ``updated_at``: this row is
    written on nearly every request, and a second timestamp that means almost
    but not quite ``last_seen_at`` is a trap for whoever reads it next.
    """

    __tablename__ = "auth_session"
    __table_args__ = (
        CheckConstraint(
            "(revoked_at IS NULL) = (revoke_reason_code IS NULL)",
            name="ck_auth_session_revoke_pair",
        ),
        # The sliding window may never outlive the hard deadline.
        CheckConstraint(
            "idle_expires_at <= absolute_expires_at", name="ck_auth_session_expiry_order"
        ),
        CheckConstraint(
            "authorization_version_at_issue > 0", name="ck_auth_session_version"
        ),
        Index(
            "ix_auth_session_account_live",
            "user_account_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        # Sweeping expired rows is a maintenance job, and it needs a cheap way
        # to find them.
        Index("ix_auth_session_absolute_expiry", "absolute_expires_at"),
    )

    #: Unpredictable, not ULID-ordered: §3.2 asks for an unpredictable id, and a
    #: time-sortable one narrows a guess to its random half.
    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_random_id("ses")
    )
    #: SHA-256 of the credential the client holds. Plain SHA-256 rather than a
    #: password KDF on purpose: the credential is 256 bits of `secrets` output,
    #: so there is no dictionary to slow an attacker down against, and a KDF
    #: here would only add per-request cost to every single API call.
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_account_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    #: Which identity proved this sign-in. §6 AUTH-07 needs it: unlinking an
    #: identity must end the sessions that identity vouched for.
    auth_identity_id: Mapped[str] = mapped_column(
        ForeignKey("auth_identity.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    idle_expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoke_reason_code: Mapped[SessionRevokeReason | None] = mapped_column(
        enum_type(SessionRevokeReason), nullable=True
    )
    authorization_version_at_issue: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: When the *provider* authenticated the human, which is not when we issued
    #: this row. §6 AUTH-06/07 require a fresh re-authentication, and "fresh"
    #: has to mean fresh at the provider, not fresh in our session table.
    auth_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: §3.2: assurance without the raw provider payload. AMR/ACR values and
    #: nothing else — a JSONB column that accepted the whole token would be
    #: filled with the whole token.
    assurance_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    #: Shown to the account holder in the security UI (§14 `UI-AUTH-04`), so it
    #: is a human label and stays minimized — "Chrome, Windows", never a
    #: fingerprint or a user-agent string.
    device_label: Mapped[str | None] = mapped_column(String(120), nullable=True)

    def is_live(self, now: dt.datetime) -> bool:
        """Revoked and expired are both dead, and §5 gives neither a way back."""
        return (
            self.revoked_at is None
            and now < self.absolute_expires_at
            and now < self.idle_expires_at
        )


class LocalPasswordCredential(Base, TimestampMixin):
    """The email+password adapter's secret, one row per local-password identity.

    This is the only password hash in the system. It hangs off the *identity*,
    not the account, because that is what it actually is: the way one provider
    — the built-in one — proves its subject. An account that also has a Google
    identity has one row here and one there, and disabling either is an unlink,
    not a schema change.
    """

    __tablename__ = "local_password_credential"

    auth_identity_id: Mapped[str] = mapped_column(
        ForeignKey("auth_identity.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


class AuthenticationEvent(Base):
    """§13's security audit of sign-in, logout, revocation and linking.

    Deliberately not the ordinary audit trail: those entries are school-scoped
    and describe what someone did *inside* a tenant, while these describe
    whether anyone got in at all, and an account can reach many schools. §13
    forbids raw email, IP, token, cookie, authorization header, provider payload
    and any child data — so none of those have a column, and the `subject_hash`
    is a keyed digest rather than the subject itself.

    Append-only by construction: no ``updated_at``, no ``version``. A security
    log that can be corrected is a security log that can be rewritten.
    """

    __tablename__ = "authentication_event"
    __table_args__ = (
        Index("ix_authentication_event_account", "user_account_id", "occurred_at"),
        Index("ix_authentication_event_correlation", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aev"))
    event_type: Mapped[AuthEventType] = mapped_column(
        enum_type(AuthEventType, length=64), nullable=False
    )
    outcome: Mapped[AuthEventOutcome] = mapped_column(
        enum_type(AuthEventOutcome), nullable=False
    )
    #: NULL for a failure that never resolved to an account — §11 keeps the
    #: response neutral, and so must the log: recording "no such account" here
    #: would rebuild the enumeration oracle in the audit trail.
    user_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    auth_identity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Pseudonymous reference to the provider subject (keyed digest), so two
    #: events can be told to be the same subject without the subject being
    #: recoverable from the log.
    subject_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The authorization version in force after the event, when the event
    #: changed it. Lets a reader reconstruct the revocation epoch history.
    authorization_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "AuthIdentity",
    "AuthSession",
    "AuthProviderRegistration",
    "AuthenticationEvent",
    "LocalPasswordCredential",
    "UserAccount",
]
