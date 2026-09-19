"""M01 §3.1–3.2 authentication enums.

Kept apart from ``identity/enums.py`` because these describe *the account*, not
the person: §2's whole point is that ``Person != UserAccount``, and a file that
holds both invites the two lifecycles to borrow each other's vocabulary.
"""

from __future__ import annotations

import enum


class UserAccountStatus(enum.StrEnum):
    """§3.1. Only ``ACTIVE`` may create or renew an application session.

    ``SUSPENDED`` is reversible, but only through ``AUTH-10`` with an M05
    permission. ``DISABLED`` is terminal in the ordinary flow and
    ``MERGED_RETIRED`` is terminal without exception — §5's transition table has
    no row leaving it, which is why it is a status and not a flag.
    """

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"
    MERGED_RETIRED = "MERGED_RETIRED"


#: Statuses that can still authenticate or be returned to authenticating, and so
#: the set that §2's "at most one non-redundant active account per person" holds
#: over. A suspended account is in here because ``AUTH-10`` can revive it: if it
#: were not, reactivation could produce a second active account for one person.
LIVE_ACCOUNT_STATUSES = (UserAccountStatus.ACTIVE, UserAccountStatus.SUSPENDED)


class AccountDisableReason(enum.StrEnum):
    """Closed reason vocabulary for ``disabled_reason_code`` (§3.1).

    §11's ``ACCOUNT_INACTIVE`` is deliberately generic to the user; the reason
    exists for the audit trail and for the platform operator, never for the
    sign-in response body.
    """

    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    LEGAL_REQUEST = "LEGAL_REQUEST"
    ACCOUNT_HOLDER_REQUEST = "ACCOUNT_HOLDER_REQUEST"
    PLATFORM_POLICY_VIOLATION = "PLATFORM_POLICY_VIOLATION"
    MERGED_INTO_ANOTHER_ACCOUNT = "MERGED_INTO_ANOTHER_ACCOUNT"
    #: Only for accounts the M01 migration carried over from the legacy
    #: `auth_account` table, which recorded that an account was disabled but
    #: never why. Naming the ignorance is better than picking a plausible
    #: reason: the reason codes above are read as findings of fact.
    UNKNOWN_LEGACY = "UNKNOWN_LEGACY"


class AccountSuspendReason(enum.StrEnum):
    """Closed reason vocabulary for ``AUTH-09`` (§6)."""

    SUSPECTED_COMPROMISE = "SUSPECTED_COMPROMISE"
    ABUSE_UNDER_REVIEW = "ABUSE_UNDER_REVIEW"
    ACCOUNT_HOLDER_REQUEST = "ACCOUNT_HOLDER_REQUEST"
    BILLING_HOLD = "BILLING_HOLD"


class IdentityUnlinkReason(enum.StrEnum):
    """Closed reason vocabulary for ``unlink_reason_code`` (§3.2, AUTH-07)."""

    ACCOUNT_HOLDER_REQUEST = "ACCOUNT_HOLDER_REQUEST"
    PROVIDER_MIGRATION = "PROVIDER_MIGRATION"
    PROVIDER_DEREGISTERED = "PROVIDER_DEREGISTERED"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    ACCOUNT_RETIRED = "ACCOUNT_RETIRED"


class AuthProviderStatus(enum.StrEnum):
    """§3.2. The registry is fail-closed: a provider that is not ``ACTIVE`` here
    cannot complete a callback, whatever the adapter or the deployment config
    says."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class AuthEventType(enum.StrEnum):
    """§13's security audit vocabulary. Never carries a credential (§2)."""

    LOGIN_STARTED = "auth.login_started"
    LOGIN_SUCCEEDED = "auth.login_succeeded"
    LOGIN_FAILED = "auth.login_failed"
    SESSION_REVOKED = "auth.session_revoked"
    LOGOUT_ALL = "auth.logout_all"
    IDENTITY_LINKED = "auth.identity_linked"
    IDENTITY_UNLINKED = "auth.identity_unlinked"
    ACCOUNT_SUSPENDED = "auth.account_suspended"
    ACCOUNT_DISABLED = "auth.account_disabled"
    AUTHORIZATION_VERSION_BUMPED = "auth.authorization_version_bumped"


class AuthEventOutcome(enum.StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


#: §3.2. The provider key of the built-in email+password adapter. It is a
#: provider like any other in the registry — §4.9 tolerates a local sign-in
#: method only when it has an explicit adapter, configuration and tests, and
#: making it a registry row is how "explicit" is enforced rather than assumed.
LOCAL_PASSWORD_PROVIDER = "local-password"

#: Its issuer. A `urn:` rather than a URL, so it can never be confused with,
#: or collide against, a real OIDC issuer in `UNIQUE(issuer, subject)`.
LOCAL_PASSWORD_ISSUER = "urn:sokola:local-password"

GOOGLE_PROVIDER = "google"
GOOGLE_ISSUER = "https://accounts.google.com"


class SessionRevokeReason(enum.StrEnum):
    """§3.2 `revoke_reason_code`, and §5's row for `aktivna → REVOKED`.

    Closed, because the reason is what a security reviewer reads months later to
    answer "why did everyone get logged out on the 14th". A free-text field
    answers that with whatever the caller was thinking at the time.
    """

    #: AUTH-04: this session, by its own holder.
    LOGOUT = "LOGOUT"
    #: AUTH-05: every session of the account, by its holder.
    LOGOUT_ALL = "LOGOUT_ALL"
    ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    ACCOUNT_MERGED = "ACCOUNT_MERGED"
    IDENTITY_LINKED = "IDENTITY_LINKED"
    IDENTITY_UNLINKED = "IDENTITY_UNLINKED"
    #: §5: a provider told us, through back-channel logout or equivalent, that
    #: the authentication behind this session no longer stands.
    PROVIDER_REVOKED = "PROVIDER_REVOKED"
    #: §4.8: M03/M05 changed what the account may reach. The session is not
    #: necessarily ended — that is their decision — but its authorization
    #: projection is not to be trusted.
    ACCESS_CHANGED = "ACCESS_CHANGED"
    SECURITY_EVENT = "SECURITY_EVENT"
    #: Not a revocation decision at all: the row was already past its idle or
    #: absolute expiry when someone presented it. §5 distinguishes EXPIRED from
    #: REVOKED, and recording expiry as a security action would bury the real
    #: ones.
    EXPIRED = "EXPIRED"


#: §13's outbox event for §4.7. PLATFORM-scoped (`school_id IS NULL`) because
#: one global account can reach many schools, and M01 must not read memberships
#: to find out which — that coupling is exactly what §13 forbids.
AUTHORIZATION_INVALIDATED_EVENT = "identity.authorization_invalidated"


class AuthCommand(enum.StrEnum):
    """§12's command scope for a receipt.

    The AUTH-nn name rather than an HTTP path: §6 defines these as commands, and
    two transports for one command must share a receipt scope or the same
    ``request_id`` would execute twice.
    """

    LOGOUT_ALL = "AUTH-05"
    LINK_IDENTITY = "AUTH-06"
    UNLINK_IDENTITY = "AUTH-07"
    SUSPEND_ACCOUNT = "AUTH-09"
    REACTIVATE_ACCOUNT = "AUTH-10"
    DISABLE_ACCOUNT = "AUTH-11"


class AuthCommandReceiptStatus(enum.StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


#: M05 permission codes §6 requires for the administrative account commands.
#: Declared here, as names, so M05 has something concrete to register rather
#: than a string invented at each call site. M01 does not check them — it has no
#: permission registry to check against, and inventing one would be M05's job
#: done badly. The HTTP surfaces for AUTH-09/10/11 wait for M05 to exist.
PERMISSION_SUSPEND_ACCOUNT = "platform.accounts.suspend"
PERMISSION_REACTIVATE_ACCOUNT = "platform.accounts.reactivate"
PERMISSION_DISABLE_ACCOUNT = "platform.accounts.disable"
