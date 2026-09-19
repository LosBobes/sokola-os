from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.organization.enums import OrganizationSchoolChangeReason
from app.domains.school.enums import (
    TYPE_TO_KIND,
    LocatorKind,
    LocatorStatus,
    MembershipStatus,
    MembershipType,
    SchoolKind,
    SchoolStatus,
    SchoolStatusReason,
    SchoolType,
)
from app.platform import clock

#: §2.0. The only values the current scope supports; the CHECKs below are what
#: make "MVP-only" a property of the database rather than of a code path someone
#: can route around.
SUPPORTED_CURRENCY = "RSD"
SUPPORTED_COUNTRY_CODE = "RS"
DEFAULT_LANGUAGE_TAG = "sr-Latn-RS"


def _kind_for(context: Any) -> tuple[SchoolKind, str | None]:
    """Derive the M04 kind from the coarse ``type`` the caller already supplied.

    Two enums describing the same thing will drift the moment one of them has a
    default the other does not, so only one of them is ever set by a caller and
    the other follows. ``TYPE_TO_KIND`` is also what the M04 migration used, so
    a school created today and one migrated yesterday classify identically.
    """
    school_type = context.get_current_parameters().get("type", SchoolType.OTHER)
    return TYPE_TO_KIND[SchoolType(school_type)]


def _school_kind_default(context: Any) -> SchoolKind:
    return _kind_for(context)[0]


def _school_kind_label_default(context: Any) -> str | None:
    return _kind_for(context)[1]


def _activated_at_default(context: Any) -> dt.datetime | None:
    """A school inserted as already ``ACTIVE`` was activated now.

    Seeds, imports and fixtures create schools in their final state rather than
    walking them through SCH-01/SCH-04, and the §2.2 CHECK says an ACTIVE school
    has an ``activated_at``. Filling it here keeps that true of every insert
    instead of only of the ones that went through the lifecycle commands.
    """
    params = context.get_current_parameters()
    return clock.now() if params.get("status") == SchoolStatus.ACTIVE else None


def _deactivated_at_default(context: Any) -> dt.datetime | None:
    params = context.get_current_parameters()
    return clock.now() if params.get("status") == SchoolStatus.DEACTIVATED else None


class School(Base, TimestampMixin):
    """A tenant. The root of the isolation boundary: nearly every other row
    carries this id and is filtered by it server-side.

    M04 §2.2 makes this the *only* operative tenant, and gives it one lifecycle
    axis, :attr:`status`. It is the projection of the last
    :class:`SchoolStatusTransition`, which is the append-only authority.
    """

    __tablename__ = "school"
    __table_args__ = (
        Index("uq_school_provisioning_reference", "provisioning_reference", unique=True),
        # The §2.2 CHECK contracts. Each one is a rule that, expressed only in
        # service code, would hold until the first import, backfill or fixture.
        CheckConstraint(
            "(school_kind = 'OTHER') = (school_kind_other_label IS NOT NULL)",
            name="ck_school_kind_other_label",
        ),
        CheckConstraint(
            "(status = 'DEACTIVATED') = (deactivated_at IS NOT NULL)",
            name="ck_school_deactivated_at",
        ),
        # activated_at is NULL only while the school has never been ACTIVE, so a
        # school that is ACTIVE or has been deactivated must carry one.
        CheckConstraint(
            "activated_at IS NOT NULL OR status = 'IN_PREPARATION'",
            name="ck_school_activated_at",
        ),
        CheckConstraint(f"currency = '{SUPPORTED_CURRENCY}'", name="ck_school_currency"),
        CheckConstraint(
            f"country_code = '{SUPPORTED_COUNTRY_CODE}'", name="ck_school_country"
        ),
        CheckConstraint("version >= 1", name="ck_school_version"),
        CheckConstraint(
            "short_name IS NULL OR length(btrim(short_name)) > 0",
            name="ck_school_short_name_not_blank",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("org"))
    #: §2.2. Globally unique platform mark of an approved school/pilot. The
    #: dedupe key for provisioning: a second request carrying the same reference
    #: is a conflict, never "here is the school you already made".
    provisioning_reference: Mapped[str] = mapped_column(
        String(64), nullable=False, default=lambda: new_id("prov")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: UI name. Never an empty string — the CHECK above says so, because ""
    #: renders as a nameless school while reading as "set".
    short_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Tenant discovery code used at login (unique). Nullable for legacy rows.
    # Superseded as the authority by SchoolLocator: this column is kept in sync
    # with the active SLUG locator so existing lookups keep working.
    slug: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    type: Mapped[SchoolType] = mapped_column(
        enum_type(SchoolType), nullable=False, default=SchoolType.OTHER
    )
    #: §2.2 ``school_kind``. Finer-grained than :attr:`type`, which predates M04
    #: and stays because existing reporting reads it.
    school_kind: Mapped[SchoolKind] = mapped_column(
        enum_type(SchoolKind), nullable=False, default=_school_kind_default
    )
    school_kind_other_label: Mapped[str | None] = mapped_column(
        String(80), nullable=True, default=_school_kind_label_default
    )
    #: §2.2, §5.2. One axis, one column. See :class:`SchoolStatus`.
    status: Mapped[SchoolStatus] = mapped_column(
        enum_type(SchoolStatus), nullable=False, default=SchoolStatus.ACTIVE
    )
    # IANA timezone; recurring schedules are interpreted against this.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Belgrade")
    #: §3.3.5. Fixed in the current scope, and fixed by a CHECK: silently
    #: converting stored money to another currency is the failure being
    #: prevented, and it cannot be prevented once the column allows the value.
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default=SUPPORTED_CURRENCY
    )
    language_tag: Mapped[str] = mapped_column(
        String(35), nullable=False, default=DEFAULT_LANGUAGE_TAG
    )
    country_code: Mapped[str] = mapped_column(
        String(2), nullable=False, default=SUPPORTED_COUNTRY_CODE
    )

    # --- Business contact (§2.2). Never the owner/identity link, and never in
    # plaintext: see app.platform.crypto for what the two key versions mean. ---
    contact_name_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Keyed HMAC of the canonical address. A dedupe key, never account linking.
    contact_email_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Which fingerprint key produced it, so a rotation does not turn every
    #: existing contact into a non-match.
    contact_email_fingerprint_key_version: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    #: The only contact value an admin screen may render.
    contact_email_masked: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Platform confirmation of the contact, required before provisioning.
    contact_verified_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Internal evidence / CRM case ref. Carries no raw contact content.
    contact_verification_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    logo_object_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: First successful activation. Never cleared on deactivation: "has this
    #: school ever operated" is a different question from "is it operating".
    activated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=_activated_at_default
    )
    deactivated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=_deactivated_at_default
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    # Payee details printed on a payment slip (uplatnica) and encoded in its
    # NBS IPS QR. All nullable: a school can run without them, it simply cannot
    # produce a slip until they are filled in (the slip endpoint says so
    # explicitly rather than emitting a half-valid QR).
    bank_account_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)


class OrganizationSchool(Base):
    """§2.3. Which organization holds a school, over time.

    A legal and commercial link, **not** an access grant (§3.1.2): no query
    anywhere may use it to decide whether someone may see a school. It is
    temporal because organizations transfer, and history has to say which entity
    held the school when a given invoice or entitlement was issued.

    Rows are never updated after they close, and never deleted.
    """

    __tablename__ = "organization_school"
    __table_args__ = (
        # At most one current link per school. Partial, because closed rows are
        # history and several of them are expected.
        Index(
            "uq_organization_school_current",
            "school_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        UniqueConstraint(
            "organization_id", "school_id", "valid_from", name="uq_organization_school_period"
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_org_school_period"),
        Index("ix_organization_school_org", "organization_id", "valid_from"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("oslk"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT"), nullable=False
    )
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    #: Half-open ``[valid_from, valid_to)``. A transfer closes the old row and
    #: opens the new one at the *same* instant, which is what keeps the history
    #: gapless without ever having two current rows.
    valid_from: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_reason_code: Mapped[OrganizationSchoolChangeReason] = mapped_column(
        enum_type(OrganizationSchoolChangeReason), nullable=False
    )
    #: Contractual / legal evidence reference. No PII payload.
    case_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchoolLocator(Base):
    """§2.4. A slug or school code pointing at a school.

    Navigation and branding only. Holding a locator creates no account, person,
    invitation, membership, role or tenant context (§3.7.4), and it is never part
    of a composite foreign key or of audit identity — the stable school id is.

    Changing one is a rotation, not an edit: the new row is inserted ACTIVE and
    the old one retired in the same transaction, so the history of what a URL
    used to mean survives.
    """

    __tablename__ = "school_locator"
    __table_args__ = (
        # Globally unique per kind, among live values. A retired slug stays in
        # the table as history and must not block a different school from taking
        # the name years later.
        Index(
            "uq_school_locator_value",
            "kind",
            "normalized_value",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        # Exactly one active locator of each kind per school.
        Index(
            "uq_school_locator_active_kind",
            "school_id",
            "kind",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        CheckConstraint(
            "(status = 'RETIRED') = (retired_at IS NOT NULL)", name="ck_school_locator_retired_at"
        ),
        CheckConstraint(
            "retired_at IS NULL OR retired_at > valid_from", name="ck_school_locator_period"
        ),
        CheckConstraint("version >= 1", name="ck_school_locator_version"),
        Index("ix_school_locator_school", "school_id", "kind", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("loc"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[LocatorKind] = mapped_column(enum_type(LocatorKind), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(63), nullable=False)
    status: Mapped[LocatorStatus] = mapped_column(
        enum_type(LocatorStatus), nullable=False, default=LocatorStatus.ACTIVE
    )
    valid_from: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Same school. Set on rotation, so an old URL can say what replaced it
    #: without that itself being a redirect into protected content (§3.7.3).
    replaced_by_locator_id: Mapped[str | None] = mapped_column(
        ForeignKey("school_locator.id", ondelete="SET NULL"), nullable=True
    )
    created_by_actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class SchoolStatusTransition(Base):
    """§2.5. The append-only authority for a school's status history.

    ``School.status`` is its projection. Keeping the history as rows rather than
    inferring it from audit text is what makes "when was this school
    deactivated, by whom, and under which reason" answerable years later, and it
    is what the §5.2 transition table is checked against.

    ``sequence_no`` starts at 1 per school and has no gaps in committed history,
    so a removed row is detectable rather than invisible.
    """

    __tablename__ = "school_status_transition"
    __table_args__ = (
        UniqueConstraint("school_id", "sequence_no", name="uq_school_status_sequence"),
        CheckConstraint("sequence_no >= 1", name="ck_school_status_sequence"),
        # Creation is the only transition with no predecessor.
        CheckConstraint(
            "(sequence_no = 1) = (from_status IS NULL)", name="ck_school_status_first"
        ),
        CheckConstraint("created_at >= effective_at", name="ck_school_status_effective"),
        Index("ix_school_status_transition_school", "school_id", "sequence_no"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("sct"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_status: Mapped[SchoolStatus | None] = mapped_column(
        enum_type(SchoolStatus), nullable=True
    )
    to_status: Mapped[SchoolStatus] = mapped_column(enum_type(SchoolStatus), nullable=False)
    #: Server commit time. Back-dated status is not supported: a status that can
    #: be asserted retroactively is not evidence of anything.
    effective_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason_code: Mapped[SchoolStatusReason] = mapped_column(
        enum_type(SchoolStatusReason), nullable=False
    )
    #: 1..500 chars, required for platform lifecycle actions. No tokens, no
    #: child or contact PII — §8.1.2.
    reason_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: The real actor. ``on_behalf_of_person_id`` never substitutes for it.
    actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    on_behalf_of_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchoolMembership(Base, TimestampMixin, RecordStatusMixin):
    """A person's belonging to a school (M06 §2.3).

    This is the relationship that makes a global Person a *member* of a tenant;
    :class:`app.domains.people.profile_models.SchoolPersonProfile` is what makes
    them known to the school at all, and the school-local code and note live
    there rather than here — a person holding three membership types has one
    code, not three.

    Ending a membership opens no new period. ``TERMINATED`` is terminal and
    coming back is a new row (§5.1): reusing the row would overwrite when the
    person was previously a member, and that history is what
    ``is_first_activation`` and every retrospective count depend on.

    Carries no ``role`` column, deliberately (§2.3). What someone may *do* is
    M05's question, answered by
    :class:`~app.domains.identity.models.RoleAssignment`.
    """

    __tablename__ = "school_membership"
    __table_args__ = (
        # One open episode per natural key. Partial on purpose: terminated rows
        # are the history, and several of them are expected.
        Index(
            "uq_school_membership_open_episode",
            "school_id",
            "person_id",
            "membership_type",
            unique=True,
            postgresql_where=text("status <> 'TERMINATED'"),
        ),
        # Tenant-safe reference keys for other modules (§2.3). Neither adds a
        # uniqueness guarantee — `id` is already the primary key — they exist so
        # a foreign key elsewhere can name the tenant as part of the reference.
        UniqueConstraint("school_id", "id", name="uq_school_membership_tenant"),
        UniqueConstraint(
            "school_id", "id", "person_id", name="uq_school_membership_tenant_person"
        ),
        # Lets a profile's foreign key require the membership's *type* as part
        # of the reference, so a participant profile on a STAFF membership is
        # impossible rather than merely incorrect (M06 §2.5, §2.6).
        UniqueConstraint(
            "school_id", "id", "membership_type", name="uq_school_membership_tenant_type"
        ),
        CheckConstraint(
            "(status = 'SUSPENDED') = (suspension_reason_code IS NOT NULL)",
            name="ck_school_membership_suspension_reason",
        ),
        CheckConstraint(
            "(status = 'TERMINATED') = (termination_reason_code IS NOT NULL)",
            name="ck_school_membership_termination_reason",
        ),
        CheckConstraint(
            "(status = 'TERMINATED') = (end_date IS NOT NULL)",
            name="ck_school_membership_end_date",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_school_membership_period",
        ),
        CheckConstraint("version >= 1", name="ck_school_membership_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mem"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        enum_type(MembershipStatus), nullable=False, default=MembershipStatus.ACTIVE
    )
    #: Participant / guardian / staff / contact. See :class:`MembershipType`.
    membership_type: Mapped[MembershipType] = mapped_column(
        enum_type(MembershipType), nullable=False, default=MembershipType.PARTICIPANT
    )
    #: The school's business date, not a timestamp: when a membership starts is
    #: a decision a school makes, and it has no time of day.
    start_date: Mapped[dt.date] = mapped_column(
        Date, nullable=False, default=lambda: clock.now().date()
    )
    end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    suspension_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    termination_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: §2.3: derived from the history of the same (school, person, type) and
    #: immutable afterwards. A returning member gets a new row with ``False``,
    #: which keeps "how many joined us for the first time this year" answerable
    #: after someone leaves and comes back.
    is_first_activation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
