"""M04 school anchor: organization, organization link, locators, status history

This lands §2.1–2.5 of the M04 master contract, and consolidates the school's
lifecycle onto one column.

Three things were previously answering "what state is this school in":
``lifecycle_status`` (IN_PREPARATION/ACTIVE), ``record_status`` (ACTIVE/ARCHIVED,
used as the deactivation switch), and, implicitly, ``onboarding_progress``.
§5.2 defines a single transition table, so there is a single ``status`` column,
and it is the projection of an append-only ``school_status_transition`` history.
The mapping is exactly the one §9.2 permits and nothing more:

    record_status ARCHIVED                 -> DEACTIVATED
    lifecycle_status IN_PREPARATION        -> IN_PREPARATION
    lifecycle_status ACTIVE                -> ACTIVE

Anything else aborts the migration rather than being guessed into a value
(§9.2: "nepoznat status ide u exception report, ne u guessed mapping").

Every existing school is given the anchor §3.1.3 and §3.7.1 say it must have had
from creation: a provisioning reference, an organization and a current link to
it, one SLUG locator, one SCHOOL_CODE locator, and status transition #1. School
ids are untouched (§9.1).

The organizations created here are placeholders: the platform has no record of
which legal entity holds these schools, and §9.5 forbids inventing one. They
carry ``case_reference = 'SELF_PROVISIONED'`` on the link so a later ORG-04
transfer can replace them with the real entity, which is what that command
exists for.

Revision ID: a4d76f2b91c0
Revises: f1c8d24b7a53
Create Date: 2026-09-18 21:10:00.000000
"""
from __future__ import annotations

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ulid import ULID

revision: str = 'a4d76f2b91c0'
down_revision: str | None = 'f1c8d24b7a53'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 8

# The coarse SchoolType this repo already stored, mapped onto the finer M04
# SchoolKind. Every source value is covered; a type with no faithful counterpart
# lands on OTHER with a label rather than being assigned a kind it is not.
TYPE_TO_KIND = {
    "SCHOOL": ("PRIVATE_SCHOOL", None),
    "SPORTS_CLUB": ("SPORTS_CLUB_ACADEMY", None),
    "DANCE_SCHOOL": ("DANCE_SCHOOL_STUDIO", None),
    "COURSE_PROVIDER": ("EDUCATION_LANGUAGE_CENTER", None),
    "EVENT_ORGANIZER": ("OTHER", "Organizator događaja"),
    "BUSINESS": ("OTHER", "Preduzeće"),
    "OTHER": ("OTHER", "Ostalo"),
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def _slugify(value: str) -> str:
    """The same normalization as app.domains.school.locator, inlined.

    Migrations are pinned history: importing the application module would make
    this migration's behaviour change whenever that module does.
    """
    import re
    import unicodedata

    spelled = unicodedata.normalize("NFKD", value.strip()).translate(
        {ord("đ"): "dj", ord("Đ"): "Dj", ord("ð"): "dj"}
    )
    ascii_only = "".join(c for c in spelled if not unicodedata.combining(c))
    lowered = ascii_only.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", lowered)).strip("-")


def _create_tables() -> None:
    op.create_table(
        "organization",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_ref", sa.String(64), nullable=False),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("registration_number", sa.String(32), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_actor_ref", sa.String(64), nullable=False),
        sa.Column("updated_by_actor_ref", sa.String(64), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="ck_organization_status"),
        sa.CheckConstraint("country_code = 'RS'", name="ck_organization_country_supported"),
        sa.CheckConstraint("length(btrim(legal_name)) BETWEEN 1 AND 200", name="ck_organization_name"),
        sa.CheckConstraint("version >= 1", name="ck_organization_version"),
    )
    op.create_index("uq_organization_ref", "organization", ["organization_ref"], unique=True)
    op.create_index(
        "uq_organization_registration",
        "organization",
        ["country_code", "registration_number"],
        unique=True,
        postgresql_where=sa.text("registration_number IS NOT NULL AND status <> 'ARCHIVED'"),
    )

    op.create_table(
        "organization_school",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organization.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("school_id", sa.String(64), sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_reason_code", sa.String(40), nullable=False),
        sa.Column("case_reference", sa.String(64), nullable=False),
        sa.Column("created_by_actor_ref", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_org_school_period"),
        sa.UniqueConstraint("organization_id", "school_id", "valid_from", name="uq_organization_school_period"),
    )
    # At most one *current* link per school. This is the constraint that makes
    # "a school belongs to exactly one organization right now" true of the data
    # and not merely of the code path that writes it.
    op.create_index(
        "uq_organization_school_current",
        "organization_school",
        ["school_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index("ix_organization_school_org", "organization_school", ["organization_id", "valid_from"])

    op.create_table(
        "school_locator",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("school_id", sa.String(64), sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("normalized_value", sa.String(63), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_locator_id", sa.String(64), sa.ForeignKey("school_locator.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_actor_ref", sa.String(64), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("kind IN ('SLUG', 'SCHOOL_CODE')", name="ck_school_locator_kind"),
        sa.CheckConstraint("status IN ('ACTIVE', 'RETIRED')", name="ck_school_locator_status"),
        sa.CheckConstraint("(status = 'RETIRED') = (retired_at IS NOT NULL)", name="ck_school_locator_retired_at"),
        sa.CheckConstraint("retired_at IS NULL OR retired_at > valid_from", name="ck_school_locator_period"),
        sa.CheckConstraint("version >= 1", name="ck_school_locator_version"),
    )
    # Unique among ACTIVE rows only: a retired slug is history, and must not
    # stop a different school from taking that name years later.
    op.create_index(
        "uq_school_locator_value",
        "school_locator",
        ["kind", "normalized_value"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_school_locator_active_kind",
        "school_locator",
        ["school_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index("ix_school_locator_school", "school_locator", ["school_id", "kind", "status"])

    op.create_table(
        "school_status_transition",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("school_id", sa.String(64), sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_no", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(40), nullable=True),
        sa.Column("to_status", sa.String(40), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("reason_note", sa.String(500), nullable=True),
        sa.Column("actor_ref", sa.String(64), nullable=False),
        sa.Column("on_behalf_of_person_id", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("school_id", "sequence_no", name="uq_school_status_sequence"),
        sa.CheckConstraint("sequence_no >= 1", name="ck_school_status_sequence"),
        sa.CheckConstraint("(sequence_no = 1) = (from_status IS NULL)", name="ck_school_status_first"),
        sa.CheckConstraint("created_at >= effective_at", name="ck_school_status_effective"),
    )
    op.create_index("ix_school_status_transition_school", "school_status_transition", ["school_id", "sequence_no"])


def _add_school_columns() -> None:
    for column in (
        sa.Column("provisioning_reference", sa.String(64), nullable=True),
        sa.Column("short_name", sa.String(80), nullable=True),
        sa.Column("school_kind", sa.String(40), nullable=True),
        sa.Column("school_kind_other_label", sa.String(80), nullable=True),
        sa.Column("status", sa.String(40), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("language_tag", sa.String(35), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("contact_name_ciphertext", sa.Text(), nullable=True),
        sa.Column("contact_email_ciphertext", sa.Text(), nullable=True),
        sa.Column("contact_email_fingerprint", sa.String(64), nullable=True),
        sa.Column("contact_email_fingerprint_key_version", sa.BigInteger(), nullable=True),
        sa.Column("contact_email_masked", sa.String(120), nullable=True),
        sa.Column("contact_phone_ciphertext", sa.Text(), nullable=True),
        sa.Column("contact_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_verification_ref", sa.String(64), nullable=True),
        sa.Column("logo_object_ref", sa.String(64), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=True),
    ):
        op.add_column("school", column)


def _map_status(lifecycle: str, record: str) -> str:
    """§9.2, and only §9.2. Unknown input raises rather than guessing."""
    if record == "ARCHIVED":
        return "DEACTIVATED"
    if record != "ACTIVE":
        raise RuntimeError(f"unmappable school record_status {record!r}; see M04 §9.2")
    if lifecycle in ("IN_PREPARATION", "ACTIVE"):
        return lifecycle
    raise RuntimeError(f"unmappable school lifecycle_status {lifecycle!r}; see M04 §9.2")


def _backfill(bind: sa.engine.Connection) -> None:
    schools = bind.execute(
        sa.text(
            "SELECT s.id, s.name, s.slug, s.type, s.lifecycle_status, s.record_status, "
            "       s.created_at, p.activated_at "
            "FROM school s LEFT JOIN onboarding_progress p ON p.school_id = s.id "
            "ORDER BY s.created_at, s.id"
        )
    ).all()

    taken_slugs: set[str] = set()
    taken_codes: set[str] = set()

    for row in schools:
        status = _map_status(row.lifecycle_status, row.record_status)
        kind, other_label = TYPE_TO_KIND[row.type]

        # activated_at is "when did this school first operate". The onboarding
        # step recorded it where it ran; older schools predate that step, so
        # their creation time is the only evidence there is, and it is used
        # rather than left NULL — NULL means "never active", which would be false.
        activated_at = None
        if status in ("ACTIVE", "DEACTIVATED"):
            activated_at = row.activated_at or row.created_at
        deactivated_at = row.created_at if status == "DEACTIVATED" else None

        bind.execute(
            sa.text(
                "UPDATE school SET provisioning_reference = :ref, school_kind = :kind, "
                "  school_kind_other_label = :label, status = :status, currency = 'RSD', "
                "  language_tag = 'sr-Latn-RS', country_code = 'RS', version = 1, "
                "  activated_at = :activated_at, deactivated_at = :deactivated_at "
                "WHERE id = :id"
            ),
            {
                "ref": _new_id("prov"),
                "kind": kind,
                "label": other_label,
                "status": status,
                "activated_at": activated_at,
                "deactivated_at": deactivated_at,
                "id": row.id,
            },
        )

        organization_id = _new_id("org")
        bind.execute(
            sa.text(
                "INSERT INTO organization (id, organization_ref, legal_name, country_code, "
                "  status, created_by_actor_ref, updated_by_actor_ref, version, created_at, updated_at) "
                "VALUES (:id, :ref, :name, 'RS', 'ACTIVE', 'migration:a4d76f2b91c0', "
                "  'migration:a4d76f2b91c0', 1, :at, :at)"
            ),
            {"id": organization_id, "ref": _new_id("oref"), "name": row.name[:200], "at": row.created_at},
        )
        bind.execute(
            sa.text(
                "INSERT INTO organization_school (id, organization_id, school_id, valid_from, "
                "  change_reason_code, case_reference, created_by_actor_ref, created_at) "
                "VALUES (:id, :org, :school, :at, 'INITIAL_PROVISIONING', 'SELF_PROVISIONED', "
                "  'migration:a4d76f2b91c0', :at)"
            ),
            {"id": _new_id("oslk"), "org": organization_id, "school": row.id, "at": row.created_at},
        )

        slug = row.slug or _slugify(row.name) or "skola"
        slug = slug[:63].strip("-") or "skola"
        if len(slug) < 3:
            slug = f"{slug}-skola"
        base = slug
        while slug in taken_slugs:
            slug = f"{base[:56]}-{secrets.token_hex(2)}"
        taken_slugs.add(slug)

        code = _generate_code(taken_codes)
        for kind_name, value in (("SLUG", slug), ("SCHOOL_CODE", code)):
            bind.execute(
                sa.text(
                    "INSERT INTO school_locator (id, school_id, kind, normalized_value, status, "
                    "  valid_from, created_by_actor_ref, version) "
                    "VALUES (:id, :school, :kind, :value, 'ACTIVE', :at, 'migration:a4d76f2b91c0', 1)"
                ),
                {"id": _new_id("loc"), "school": row.id, "kind": kind_name, "value": value, "at": row.created_at},
            )
        # Keep the operative slug column in step with the locator that is now
        # its authority; they must not be able to disagree.
        bind.execute(sa.text("UPDATE school SET slug = :slug WHERE id = :id"), {"slug": slug, "id": row.id})

        # Transition #1 records the school as it exists now, not a replayed
        # history: the earlier transitions were never recorded and §2.5 forbids
        # back-dating a status, so inventing them would be inventing evidence.
        bind.execute(
            sa.text(
                "INSERT INTO school_status_transition (id, school_id, sequence_no, from_status, "
                "  to_status, effective_at, reason_code, reason_note, actor_ref, correlation_id, created_at) "
                "VALUES (:id, :school, 1, NULL, :status, :at, 'SCHOOL_CREATED', :note, "
                "  'migration:a4d76f2b91c0', :corr, :at)"
            ),
            {
                "id": _new_id("sct"),
                "school": row.id,
                "status": status,
                "at": row.created_at,
                "note": "Migracija M04: zatečeni status škole, bez rekonstruisane istorije.",
                "corr": _new_id("corr"),
            },
        )


def _generate_code(taken: set[str]) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in taken:
            taken.add(code)
            return code


def _finalize_school() -> None:
    """Tighten the new columns and drop the two the status column replaces."""
    for column in (
        "provisioning_reference",
        "school_kind",
        "status",
        "currency",
        "language_tag",
        "country_code",
        "version",
    ):
        op.alter_column("school", column, nullable=False)

    op.drop_column("school", "lifecycle_status")
    op.drop_column("school", "record_status")

    op.create_index("uq_school_provisioning_reference", "school", ["provisioning_reference"], unique=True)
    for name, expression in (
        ("ck_school_kind_other_label", "(school_kind = 'OTHER') = (school_kind_other_label IS NOT NULL)"),
        ("ck_school_deactivated_at", "(status = 'DEACTIVATED') = (deactivated_at IS NOT NULL)"),
        ("ck_school_activated_at", "activated_at IS NOT NULL OR status = 'IN_PREPARATION'"),
        ("ck_school_currency", "currency = 'RSD'"),
        ("ck_school_country", "country_code = 'RS'"),
        ("ck_school_version", "version >= 1"),
        ("ck_school_short_name_not_blank", "short_name IS NULL OR length(btrim(short_name)) > 0"),
        ("ck_school_status", "status IN ('IN_PREPARATION', 'ACTIVE', 'DEACTIVATED')"),
        (
            "ck_school_kind",
            "school_kind IN ('PRIVATE_SCHOOL', 'SPORTS_CLUB_ACADEMY', 'DANCE_SCHOOL_STUDIO', "
            "'MUSIC_SCHOOL', 'ART_DRAMA_SCHOOL', 'EDUCATION_LANGUAGE_CENTER', "
            "'ACTIVITY_WORKSHOP_CENTER', 'OTHER')",
        ),
    ):
        op.execute(f'ALTER TABLE school ADD CONSTRAINT "{name}" CHECK ({expression})')


def upgrade() -> None:
    bind = op.get_bind()
    _create_tables()
    _add_school_columns()
    _backfill(bind)
    _finalize_school()


def downgrade() -> None:
    op.add_column("school", sa.Column("lifecycle_status", sa.String(40), nullable=True))
    op.add_column("school", sa.Column("record_status", sa.String(40), nullable=True))
    op.execute(
        "UPDATE school SET "
        "  lifecycle_status = CASE WHEN status = 'IN_PREPARATION' THEN 'IN_PREPARATION' ELSE 'ACTIVE' END, "
        "  record_status = CASE WHEN status = 'DEACTIVATED' THEN 'ARCHIVED' ELSE 'ACTIVE' END"
    )
    op.alter_column("school", "lifecycle_status", nullable=False)
    op.alter_column("school", "record_status", nullable=False)

    op.drop_index("uq_school_provisioning_reference", table_name="school")
    for name in (
        "ck_school_kind_other_label",
        "ck_school_deactivated_at",
        "ck_school_activated_at",
        "ck_school_currency",
        "ck_school_country",
        "ck_school_version",
        "ck_school_short_name_not_blank",
        "ck_school_status",
        "ck_school_kind",
    ):
        op.execute(f'ALTER TABLE school DROP CONSTRAINT IF EXISTS "{name}"')
    for column in (
        "provisioning_reference", "short_name", "school_kind", "school_kind_other_label",
        "status", "currency", "language_tag", "country_code", "contact_name_ciphertext",
        "contact_email_ciphertext", "contact_email_fingerprint",
        "contact_email_fingerprint_key_version", "contact_email_masked",
        "contact_phone_ciphertext", "contact_verified_at", "contact_verification_ref",
        "logo_object_ref", "activated_at", "deactivated_at", "version",
    ):
        op.drop_column("school", column)

    op.drop_table("school_status_transition")
    op.drop_table("school_locator")
    op.drop_table("organization_school")
    op.drop_table("organization")
