from __future__ import annotations

import datetime as dt

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
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.identity.enums import (
    AuthAccountStatus,
    AuthIdentifierType,
    InvitationStatus,
    InvitationType,
    PersonDedupeStatus,
    PersonIdentityStatus,
    PersonMergeStatus,
    RoleAssignmentStatus,
    RoleCode,
    RoleScopeType,
)


class Person(Base, TimestampMixin, RecordStatusMixin):
    """A global human identity. Existing globally does NOT make a person visible
    to any school; visibility comes only through an org-scoped relationship.

    M06 §2.1. Carries no password, provider subject, role, ``school_id`` or auth
    status: M01 owns the link between an account and a person, and this table is
    not it. The contact columns here are *contact*, never a login or link key —
    :class:`AuthIdentifier` is what a sign-in resolves through, and the two are
    deliberately different columns holding differently-protected values.
    """

    __tablename__ = "person"
    __table_args__ = (
        # §2.1: the ciphertext and its blind index travel together. One without
        # the other is either a contact nobody can deduplicate or an index
        # pointing at nothing, and both are silent failures.
        CheckConstraint(
            "(email_ciphertext IS NULL) = (email_blind_index IS NULL)",
            name="ck_person_email_pair",
        ),
        CheckConstraint(
            "(phone_ciphertext IS NULL) = (phone_blind_index IS NULL)",
            name="ck_person_phone_pair",
        ),
        # §2.1: filled only when MERGED, and never pointing at itself.
        CheckConstraint(
            "(dedupe_status = 'MERGED') = (merged_into_person_id IS NOT NULL)",
            name="ck_person_merged_into",
        ),
        CheckConstraint(
            "merged_into_person_id IS NULL OR merged_into_person_id <> id",
            name="ck_person_merged_not_self",
        ),
        CheckConstraint("version >= 1", name="ck_person_version"),
        # Candidate lookup, never a uniqueness claim: §3.4 says two real people
        # may share a contact, so this index must not be unique.
        Index("ix_person_email_blind_index", "email_blind_index"),
        Index("ix_person_phone_blind_index", "phone_blind_index"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("per"))
    given_name: Mapped[str] = mapped_column(String(120), nullable=False)
    family_name: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    #: §2.1: unknown is allowed, and for the age guard it means "age is not
    #: proven" — which §3.1 turns into NOT_ELIGIBLE rather than into a guess.
    birth_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    identity_status: Mapped[PersonIdentityStatus] = mapped_column(
        enum_type(PersonIdentityStatus), nullable=False, default=PersonIdentityStatus.PROVISIONAL
    )

    # --- Contact (§2.1). Encrypted at the field, indexed by blind index. See
    # app.platform.crypto: the ciphertext carries its own key version, and the
    # blind index is keyed by a *separate* key so the index cannot be reversed
    # by anyone who only has the encryption key. ---
    email_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_blind_index: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_blind_index_key_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    phone_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_blind_index: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_blind_index_key_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    dedupe_status: Mapped[PersonDedupeStatus] = mapped_column(
        enum_type(PersonDedupeStatus), nullable=False, default=PersonDedupeStatus.CLEAR
    )
    merged_into_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class AuthAccount(Base, TimestampMixin):
    """A Person's credentials and their link to any identity provider. The only
    auth authority: both sign-in methods (password and Google) resolve to
    exactly one of these rows per person."""

    __tablename__ = "auth_account"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aac"))
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="oidc")
    status: Mapped[AuthAccountStatus] = mapped_column(
        enum_type(AuthAccountStatus), nullable=False, default=AuthAccountStatus.ACTIVE
    )
    # Local email+password credential (scrypt hash, see app.security.password).
    # NULL for accounts that authenticate only via Google, the two are not
    # mutually exclusive: an account can carry a password AND a linked OIDC
    # subject for the same person.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AuthIdentifier(Base, TimestampMixin):
    """A resolvable external identifier (OIDC subject / email / phone) for lookup.
    Identifiers are lookup keys only, any password hash lives on the
    :class:`AuthAccount`, never here."""

    __tablename__ = "auth_identifier"
    __table_args__ = (UniqueConstraint("type", "value", name="uq_auth_identifier"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aid"))
    auth_account_id: Mapped[str] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[AuthIdentifierType] = mapped_column(
        enum_type(AuthIdentifierType), nullable=False
    )
    value: Mapped[str] = mapped_column(String(320), nullable=False)


class RoleAssignment(Base, TimestampMixin, RecordStatusMixin):
    """What a person is allowed to do inside one school. ``role_code`` is a
    closed access-template facade, never a job title. This is the authority the
    server consults to build the request context."""

    __tablename__ = "role_assignment"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "school_id",
            "role_code",
            "scope_type",
            "scope_ref_id",
            name="uq_role_assignment",
        ),
        # Tenant + person + role as a referenceable key, so a foreign key
        # elsewhere can require all four at once (see
        # school_primary_owner_term). Uniqueness is already given by the primary
        # key; what this adds is the ability to point at it *with* its context.
        UniqueConstraint(
            "school_id",
            "id",
            "person_id",
            "role_code",
            name="uq_role_assignment_tenant_person_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rol"))
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    role_code: Mapped[RoleCode] = mapped_column(enum_type(RoleCode), nullable=False)
    scope_type: Mapped[RoleScopeType] = mapped_column(
        enum_type(RoleScopeType), nullable=False, default=RoleScopeType.SCHOOL
    )
    # Branch/group id when the role is narrower than the whole school.
    scope_ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[RoleAssignmentStatus] = mapped_column(
        enum_type(RoleAssignmentStatus), nullable=False, default=RoleAssignmentStatus.ACTIVE
    )
    # Per-assignment area restriction (see app.security.permissions). NULL = the
    # role's full default areas; a list narrows this assignment to those area
    # codes only (e.g. an ADMIN invited "for finances only"). Never an escalation.
    granted_areas: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(40)), nullable=True
    )


class StudentLoginAuthorization(Base, TimestampMixin):
    """Separates a child's identity from permission to log in. A Person can exist
    (and be scheduled/billed) long before, or without, being allowed to sign in."""

    __tablename__ = "student_login_authorization"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("sla"))
    student_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    login_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    authorized_by_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Invitation(Base, TimestampMixin):
    """An invitation to claim access. Invitations expire and may be reissued.

    ``role_code``/``scope_type``/``scope_ref_id``/``granted_areas`` describe the
    :class:`RoleAssignment` that acceptance will create, an invitation is an
    offer of a specific role, not a blank slate. ``target_child_person_id`` is
    set only for a PARENT invitation (§19.4/19.5): the child the invited
    guardian will get access to.
    """

    __tablename__ = "invitation"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_invitation_token_hash"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("inv"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[InvitationType] = mapped_column(enum_type(InvitationType), nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        enum_type(InvitationStatus), nullable=False, default=InvitationStatus.PENDING
    )
    # Set once acceptance resolves to a Person (never set at send time).
    person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # The role assignment acceptance will create (or reactivate).
    role_code: Mapped[RoleCode] = mapped_column(enum_type(RoleCode), nullable=False)
    scope_type: Mapped[RoleScopeType] = mapped_column(
        enum_type(RoleScopeType), nullable=False, default=RoleScopeType.SCHOOL
    )
    scope_ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    granted_areas: Mapped[list[str] | None] = mapped_column(ARRAY(String(40)), nullable=True)

    # PARENT invites only: the child this guardian will be linked to.
    target_child_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invited_by_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Reissuing supersedes a PENDING/EXPIRED invitation with a fresh row/token;
    # this points back at the one it replaced (chain, not mutation-in-place).
    reissued_from_invitation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PersonMergeRecord(Base, TimestampMixin):
    """A duplicate-review case, and (once decided) append-only evidence of a
    merge. There is no self-service dedup endpoint; merges are deliberate,
    reviewed operations scoped to the school that raised them."""

    __tablename__ = "person_merge_record"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mrg"))
    # The tenant that flagged the pair; the review never crosses org boundaries.
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    source_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PersonMergeStatus] = mapped_column(
        enum_type(PersonMergeStatus), nullable=False, default=PersonMergeStatus.FLAGGED
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Who raised the case at intake, and who decided it.
    flagged_by_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    performed_by_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Workspace(Base, TimestampMixin, RecordStatusMixin):
    """Reserved commercial/ownership container. No subscriptions or entitlements
    in P0, present so the model is future-shaped, not future-built."""

    __tablename__ = "workspace"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("wsp"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
