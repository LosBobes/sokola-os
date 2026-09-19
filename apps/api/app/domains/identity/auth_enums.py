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
