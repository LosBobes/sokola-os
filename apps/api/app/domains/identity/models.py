from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
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
    PersonIdentityStatus,
    RoleAssignmentStatus,
    RoleCode,
    RoleScopeType,
)


class Person(Base, TimestampMixin, RecordStatusMixin):
    """A global human identity. Existing globally does NOT make a person visible
    to any organization; visibility comes only through an org-scoped relationship."""

    __tablename__ = "person"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("per"))
    given_name: Mapped[str] = mapped_column(String(120), nullable=False)
    family_name: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    identity_status: Mapped[PersonIdentityStatus] = mapped_column(
        enum_type(PersonIdentityStatus), nullable=False, default=PersonIdentityStatus.PROVISIONAL
    )


class AuthAccount(Base, TimestampMixin):
    """Links a Person to an external identity provider. The only auth authority."""

    __tablename__ = "auth_account"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aac"))
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="oidc")
    status: Mapped[AuthAccountStatus] = mapped_column(
        enum_type(AuthAccountStatus), nullable=False, default=AuthAccountStatus.ACTIVE
    )


class AuthIdentifier(Base, TimestampMixin):
    """A resolvable external identifier (OIDC subject / email / phone) for lookup.
    We store links, never local password hashes or reset tokens."""

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
    """What a person is allowed to do inside one organization. ``role_code`` is a
    closed access-template facade, never a job title. This is the authority the
    server consults to build the request context."""

    __tablename__ = "role_assignment"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "organization_id",
            "role_code",
            "scope_type",
            "scope_ref_id",
            name="uq_role_assignment",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rol"))
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    role_code: Mapped[RoleCode] = mapped_column(enum_type(RoleCode), nullable=False)
    scope_type: Mapped[RoleScopeType] = mapped_column(
        enum_type(RoleScopeType), nullable=False, default=RoleScopeType.ORGANIZATION
    )
    # Branch/group id when the role is narrower than the whole organization.
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
    """An invitation to claim access. Invitations expire and may be reissued."""

    __tablename__ = "invitation"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("inv"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[InvitationType] = mapped_column(enum_type(InvitationType), nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        enum_type(InvitationStatus), nullable=False, default=InvitationStatus.PENDING
    )
    person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PersonMergeRecord(Base, TimestampMixin):
    """Append-only evidence of a merge. There is no self-service dedup endpoint;
    merges are deliberate, reviewed operations."""

    __tablename__ = "person_merge_record"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mrg"))
    source_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    performed_by_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Workspace(Base, TimestampMixin, RecordStatusMixin):
    """Reserved commercial/ownership container. No subscriptions or entitlements
    in P0 — present so the model is future-shaped, not future-built."""

    __tablename__ = "workspace"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("wsp"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
