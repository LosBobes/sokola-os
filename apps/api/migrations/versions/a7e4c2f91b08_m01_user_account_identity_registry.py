"""M01 account, provider identity and the fail-closed provider registry

M01 §3.1–3.2, §15.

Replaces `auth_account` / `auth_identifier` with the M01 model:

* `user_account` — the thing that signs in, with the `authorization_version`
  §4.7 makes the revocation epoch. Carries no password, no token, no tenant and
  no role, per §3.1's forbidden list.
* `auth_provider_registration` — §3.2's fail-closed registry. Nothing can
  complete a callback for an issuer that has no ACTIVE row here.
* `auth_identity` — one verified link to one provider subject, with
  `UNIQUE(provider_issuer, provider_subject)` *global*, which is what makes
  "one external subject reaches one account" (§4.3) a database fact.
* `local_password_credential` — the email+password adapter's hash, moved off
  the account row so §3.1's ban is literal.
* `authentication_event` — §13's security log, append-only, with no column that
  could hold a token, an email, an IP or a raw provider payload.

Backfill (§15), deterministic and idempotent:

* one `user_account` per `auth_account`, reusing the ULID so a re-run is a
  no-op and so an operator can trace a row back to what it was;
* each SUBJECT identifier becomes a Google `auth_identity`, keeping its own id;
* an account carrying a password hash gains a `local-password` identity whose
  subject is the account id — the local provider is the only one whose subjects
  we mint, and minting them from the account keeps them stable and unique
  without a random value that a re-run would change;
* EMAIL identifiers do not survive as identities. §2 is explicit that a contact
  email is not a login identity; the address is carried onto the identity it
  belonged to as `login_email`, the minimized snapshot §3.2 permits.

Nothing is merged and nothing is guessed. A disabled legacy account gets
`disabled_reason_code = 'UNKNOWN_LEGACY'` rather than a plausible-looking
reason, and any row the backfill cannot place deterministically is left behind
and counted in the report this migration prints, per §15's requirement for an
exception report without an automatic merge.

Revision ID: a7e4c2f91b08
Revises: f3c92d81ab45
Create Date: 2026-09-19 13:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7e4c2f91b08'
down_revision: str | None = 'f3c92d81ab45'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCOUNT_STATUSES = "('ACTIVE', 'SUSPENDED', 'DISABLED', 'MERGED_RETIRED')"
_LIVE = "('ACTIVE', 'SUSPENDED')"
_DISABLE_REASONS = (
    "('SECURITY_INCIDENT', 'LEGAL_REQUEST', 'ACCOUNT_HOLDER_REQUEST', "
    "'PLATFORM_POLICY_VIOLATION', 'MERGED_INTO_ANOTHER_ACCOUNT', 'UNKNOWN_LEGACY')"
)
_UNLINK_REASONS = (
    "('ACCOUNT_HOLDER_REQUEST', 'PROVIDER_MIGRATION', 'PROVIDER_DEREGISTERED', "
    "'SECURITY_INCIDENT', 'ACCOUNT_RETIRED')"
)
_PROVIDER_STATUSES = "('ACTIVE', 'DISABLED')"
_EVENT_TYPES = (
    "('auth.login_started', 'auth.login_succeeded', 'auth.login_failed', "
    "'auth.session_revoked', 'auth.logout_all', 'auth.identity_linked', "
    "'auth.identity_unlinked', 'auth.account_suspended', 'auth.account_disabled', "
    "'auth.authorization_version_bumped')"
)
_EVENT_OUTCOMES = "('SUCCEEDED', 'FAILED')"

GOOGLE_ISSUER = "https://accounts.google.com"
LOCAL_ISSUER = "urn:sokola:local-password"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "person_id", sa.String(64),
            sa.ForeignKey("person.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("authorization_version", sa.BigInteger(), nullable=False),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_reason_code", sa.String(40), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            f"status IN {_ACCOUNT_STATUSES}", name="ck_user_account_status_enum"
        ),
        sa.CheckConstraint(
            f"disabled_reason_code IS NULL OR disabled_reason_code IN {_DISABLE_REASONS}",
            name="ck_user_account_disable_reason_enum",
        ),
        sa.CheckConstraint(
            "authorization_version > 0", name="ck_user_account_auth_version"
        ),
        sa.CheckConstraint("version > 0", name="ck_user_account_version"),
        sa.CheckConstraint(
            "(disabled_at IS NULL) = (disabled_reason_code IS NULL)",
            name="ck_user_account_disabled_pair",
        ),
        sa.CheckConstraint(
            f"(status IN {_LIVE}) = (disabled_at IS NULL)",
            name="ck_user_account_disabled_status",
        ),
    )
    op.create_index("ix_user_account_person_id", "user_account", ["person_id"])
    op.create_index(
        "uq_user_account_live_person",
        "user_account",
        ["person_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN {_LIVE}"),
    )

    op.create_table(
        "auth_provider_registration",
        sa.Column("provider_key", sa.String(64), primary_key=True),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("allowed_audiences", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("allowed_redirect_uris", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("allowed_algorithms", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("discovery_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("config_revision", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            f"status IN {_PROVIDER_STATUSES}", name="ck_auth_provider_status_enum"
        ),
        sa.CheckConstraint(
            "config_revision > 0", name="ck_auth_provider_config_revision"
        ),
        sa.CheckConstraint(
            "cardinality(allowed_algorithms) > 0", name="ck_auth_provider_algorithms"
        ),
    )
    op.create_index(
        "uq_auth_provider_active_issuer",
        "auth_provider_registration",
        ["issuer"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "authentication_event",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column(
            "user_account_id", sa.String(64),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("auth_identity_id", sa.String(64), nullable=True),
        sa.Column("provider_key", sa.String(64), nullable=True),
        sa.Column("subject_hash", sa.String(64), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("authorization_version", sa.BigInteger(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"event_type IN {_EVENT_TYPES}", name="ck_authentication_event_type_enum"
        ),
        sa.CheckConstraint(
            f"outcome IN {_EVENT_OUTCOMES}", name="ck_authentication_event_outcome_enum"
        ),
    )
    op.create_index(
        "ix_authentication_event_account",
        "authentication_event",
        ["user_account_id", "occurred_at"],
    )
    op.create_index(
        "ix_authentication_event_correlation", "authentication_event", ["correlation_id"]
    )

    op.create_table(
        "auth_identity",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_account_id", sa.String(64),
            sa.ForeignKey("user_account.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "provider_key", sa.String(64),
            sa.ForeignKey("auth_provider_registration.provider_key", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider_issuer", sa.Text(), nullable=False),
        sa.Column("provider_subject", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("login_email", sa.String(320), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlink_reason_code", sa.String(40), nullable=True),
        sa.Column(
            "created_by_event_id", sa.String(64),
            sa.ForeignKey("authentication_event.id", ondelete="SET NULL"), nullable=True,
        ),
        *_timestamps(),
        sa.UniqueConstraint(
            "provider_issuer", "provider_subject", name="uq_auth_identity_subject"
        ),
        sa.CheckConstraint(
            f"unlink_reason_code IS NULL OR unlink_reason_code IN {_UNLINK_REASONS}",
            name="ck_auth_identity_unlink_reason_enum",
        ),
        sa.CheckConstraint(
            "(unlinked_at IS NULL) = (unlink_reason_code IS NULL)",
            name="ck_auth_identity_unlink_pair",
        ),
        sa.CheckConstraint(
            "email_verified_at IS NULL OR login_email IS NOT NULL",
            name="ck_auth_identity_verified_needs_email",
        ),
        sa.CheckConstraint(
            "provider_key <> 'local-password' OR login_email IS NOT NULL",
            name="ck_auth_identity_local_needs_email",
        ),
    )
    op.create_index(
        "ix_auth_identity_account_live",
        "auth_identity",
        ["user_account_id"],
        postgresql_where=sa.text("unlinked_at IS NULL"),
    )
    op.execute(
        "CREATE INDEX ix_auth_identity_login_email "
        "ON auth_identity (lower(login_email))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_auth_identity_local_email "
        "ON auth_identity (lower(login_email)) "
        "WHERE provider_key = 'local-password' AND unlinked_at IS NULL"
    )

    op.create_table(
        "local_password_credential",
        sa.Column(
            "auth_identity_id", sa.String(64),
            sa.ForeignKey("auth_identity.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("password_hash", sa.String(255), nullable=False),
        *_timestamps(),
    )

    _seed_providers()
    _backfill()


def _seed_providers() -> None:
    """The two adapters the repo actually has.

    Audiences and redirect URIs start empty on purpose. They are deployment
    facts (this environment's client id, this environment's callback URL), and
    writing a guess here would be worse than an empty allowlist: an empty
    allowlist fails closed, a wrong one fails open. `sync_provider_registry`
    reconciles them from settings at boot.
    """
    op.execute(
        sa.text(
            """
            INSERT INTO auth_provider_registration (
                provider_key, issuer, allowed_audiences, allowed_redirect_uris,
                allowed_algorithms, discovery_url, status, config_revision
            ) VALUES
                ('google', :google_issuer, '{}', '{}', '{RS256}',
                 'https://accounts.google.com/.well-known/openid-configuration',
                 'ACTIVE', 1),
                ('local-password', :local_issuer, '{}', '{}', '{scrypt}',
                 NULL, 'ACTIVE', 1)
            ON CONFLICT (provider_key) DO NOTHING
            """
        ).bindparams(google_issuer=GOOGLE_ISSUER, local_issuer=LOCAL_ISSUER)
    )


def _backfill() -> None:
    bind = op.get_bind()

    # One account per legacy account, ULID preserved. `aac_X` -> `uac_X`.
    bind.execute(
        sa.text(
            """
            INSERT INTO user_account (
                id, person_id, status, authorization_version,
                disabled_at, disabled_reason_code, version, created_at, updated_at
            )
            SELECT
                'uac_' || substr(a.id, 5),
                a.person_id,
                CASE WHEN a.status = 'DISABLED' THEN 'DISABLED' ELSE 'ACTIVE' END,
                1,
                CASE WHEN a.status = 'DISABLED' THEN a.updated_at END,
                CASE WHEN a.status = 'DISABLED' THEN 'UNKNOWN_LEGACY' END,
                1,
                a.created_at,
                a.updated_at
            FROM auth_account a
            ON CONFLICT (id) DO NOTHING
            """
        )
    )

    # The address an account signed in with, if it had exactly one. More than
    # one is not a merge decision this migration is allowed to make, so those
    # accounts carry no `login_email` and are named in the report below.
    single_email = """
        SELECT auth_account_id, min(value) AS value
        FROM auth_identifier
        WHERE type = 'EMAIL'
        GROUP BY auth_account_id
        HAVING count(*) = 1
    """

    # SUBJECT identifiers become Google identities, keeping their own id.
    bind.execute(
        sa.text(
            f"""
            INSERT INTO auth_identity (
                id, user_account_id, provider_key, provider_issuer, provider_subject,
                login_email, linked_at, last_verified_at, created_at, updated_at
            )
            SELECT
                i.id,
                'uac_' || substr(i.auth_account_id, 5),
                'google',
                :google_issuer,
                i.value,
                e.value,
                i.created_at,
                i.updated_at,
                i.created_at,
                i.updated_at
            FROM auth_identifier i
            LEFT JOIN ({single_email}) e ON e.auth_account_id = i.auth_account_id
            WHERE i.type = 'SUBJECT'
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(google_issuer=GOOGLE_ISSUER)
    )

    # A password hash becomes a `local-password` identity whose subject is the
    # account id: stable across email changes, unique by construction, and
    # never derived from the address (§2 — an email is not a login identity).
    # An account with no single unambiguous address is skipped; it could not
    # have signed in by password anyway, and the report counts it.
    bind.execute(
        sa.text(
            f"""
            INSERT INTO auth_identity (
                id, user_account_id, provider_key, provider_issuer, provider_subject,
                login_email, linked_at, created_at, updated_at
            )
            SELECT
                'aid_' || substr(a.id, 5),
                'uac_' || substr(a.id, 5),
                'local-password',
                :local_issuer,
                'uac_' || substr(a.id, 5),
                lower(e.value),
                a.created_at,
                a.created_at,
                a.updated_at
            FROM auth_account a
            JOIN ({single_email}) e ON e.auth_account_id = a.id
            WHERE a.password_hash IS NOT NULL
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(local_issuer=LOCAL_ISSUER)
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO local_password_credential (auth_identity_id, password_hash)
            SELECT 'aid_' || substr(a.id, 5), a.password_hash
            FROM auth_account a
            JOIN auth_identity ai ON ai.id = 'aid_' || substr(a.id, 5)
            WHERE a.password_hash IS NOT NULL
            ON CONFLICT (auth_identity_id) DO NOTHING
            """
        )
    )

    _report(bind)

    op.drop_table("auth_identifier")
    op.drop_table("auth_account")


def _report(bind: sa.engine.Connection) -> None:
    """§15's exception report. Prints rather than repairs.

    Every case here is one where picking an answer would mean asserting
    something about a real person's sign-in that nobody told us. They are left
    for an operator, which is the whole difference between a backfill and a
    merge.
    """
    ambiguous = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM (
                SELECT auth_account_id FROM auth_identifier WHERE type = 'EMAIL'
                GROUP BY auth_account_id HAVING count(*) > 1
            ) x
            """
        )
    ).scalar_one()
    password_without_email = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM auth_account a
            WHERE a.password_hash IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM auth_identifier i
                WHERE i.auth_account_id = a.id AND i.type = 'EMAIL'
                GROUP BY i.auth_account_id HAVING count(*) = 1
              )
            """
        )
    ).scalar_one()
    orphan_identifiers = bind.execute(
        sa.text(
            "SELECT count(*) FROM auth_identifier WHERE type NOT IN ('EMAIL', 'SUBJECT')"
        )
    ).scalar_one()
    accounts = bind.execute(sa.text("SELECT count(*) FROM user_account")).scalar_one()
    identities = bind.execute(sa.text("SELECT count(*) FROM auth_identity")).scalar_one()

    print(
        "\n[M01 backfill report]"
        f"\n  user_account rows:                      {accounts}"
        f"\n  auth_identity rows:                     {identities}"
        f"\n  accounts with ambiguous email (skipped):{ambiguous}"
        f"\n  password accounts with no single email: {password_without_email}"
        f"\n  non-email/subject identifiers dropped:  {orphan_identifiers}"
        "\n  Skipped rows were not merged or guessed; they need an operator"
        " decision before those people can sign in again.\n"
    )


def downgrade() -> None:
    op.create_table(
        "auth_account",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "person_id", sa.String(64),
            sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False, unique=True,
        ),
        sa.Column("provider", sa.String(64), nullable=False, server_default="oidc"),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')", name="ck_auth_account_status_enum"
        ),
    )
    op.create_table(
        "auth_identifier",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "auth_account_id", sa.String(64),
            sa.ForeignKey("auth_account.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("value", sa.String(320), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("type", "value", name="uq_auth_identifier"),
        sa.CheckConstraint(
            "type IN ('SUBJECT', 'EMAIL', 'PHONE')", name="ck_auth_identifier_type_enum"
        ),
    )

    bind = op.get_bind()
    # Only ACTIVE/DISABLED existed before; a SUSPENDED or MERGED_RETIRED account
    # has no legacy representation, and the nearest one that cannot restore
    # access is DISABLED. Going down is lossy on purpose: the alternative is
    # reactivating an account somebody deliberately suspended.
    bind.execute(
        sa.text(
            """
            INSERT INTO auth_account (
                id, person_id, provider, status, password_hash, created_at, updated_at
            )
            SELECT
                'aac_' || substr(u.id, 5),
                u.person_id,
                CASE WHEN c.password_hash IS NOT NULL THEN 'password' ELSE 'oidc' END,
                CASE WHEN u.status = 'ACTIVE' THEN 'ACTIVE' ELSE 'DISABLED' END,
                c.password_hash,
                u.created_at,
                u.updated_at
            FROM user_account u
            LEFT JOIN auth_identity li
                ON li.user_account_id = u.id
               AND li.provider_key = 'local-password'
               AND li.unlinked_at IS NULL
            LEFT JOIN local_password_credential c ON c.auth_identity_id = li.id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO auth_identifier (id, auth_account_id, type, value, created_at, updated_at)
            SELECT
                ai.id,
                'aac_' || substr(ai.user_account_id, 5),
                'SUBJECT',
                ai.provider_subject,
                ai.created_at,
                ai.updated_at
            FROM auth_identity ai
            WHERE ai.provider_key = 'google'
            """
        )
    )
    # One email row per account, the first by identity id, because the legacy
    # UNIQUE(type, value) cannot hold two accounts sharing an address and the
    # new model deliberately can.
    bind.execute(
        sa.text(
            """
            INSERT INTO auth_identifier (id, auth_account_id, type, value, created_at, updated_at)
            SELECT DISTINCT ON (lower(ai.login_email))
                'aie_' || substr(ai.id, 5),
                'aac_' || substr(ai.user_account_id, 5),
                'EMAIL',
                lower(ai.login_email),
                ai.created_at,
                ai.updated_at
            FROM auth_identity ai
            WHERE ai.login_email IS NOT NULL
            ORDER BY lower(ai.login_email), ai.id
            """
        )
    )

    op.drop_table("local_password_credential")
    op.drop_table("auth_identity")
    op.drop_table("authentication_event")
    op.drop_table("auth_provider_registration")
    op.drop_table("user_account")
