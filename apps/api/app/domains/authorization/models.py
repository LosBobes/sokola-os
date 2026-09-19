"""M05 §2.2–2.4: the authorization policy registry.

Reference data, not tenant data. None of these tables carries a `school_id`:
a permission catalogue is the same catalogue for every school, and giving it a
tenant column would invite per-school policy, which §3.2 point 3 rules out —
a new permission is default-deny for every role until a published revision
says otherwise.

What a *person* holds is separate and already exists: `RoleAssignment` in the
identity domain. This module says what a role key *means*.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.authorization.enums import (
    AssignmentPolicy,
    AuthorizationDomainStatus,
    ChildDataClass,
    DelegationClass,
    OfflinePolicy,
    PermissionStatus,
    PolicyChangeReason,
    PolicyRevisionStatus,
    RiskLevel,
    RoleDefinitionStatus,
)


class AuthorizationPolicyRevision(Base, TimestampMixin):
    """§2.2. One published catalogue of permissions, roles and bindings.

    Exactly one is `ACTIVE` — enforced by a partial unique index rather than
    by application care, because "exactly one" is the kind of invariant that
    survives precisely as long as nobody writes a second code path.
    """

    __tablename__ = "authorization_policy_revision"
    __table_args__ = (
        UniqueConstraint("revision_no", name="uq_policy_revision_no"),
        Index(
            "uq_policy_revision_single_active",
            "status",
            unique=True,
            postgresql_where="status = 'ACTIVE'",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pol"))
    #: Globally unique and strictly increasing (§2.2).
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PolicyRevisionStatus] = mapped_column(
        enum_type(PolicyRevisionStatus), nullable=False, default=PolicyRevisionStatus.DRAFT
    )
    #: SHA-256 over the canonical permission/role/binding content. A published
    #: revision is immutable, and this is what makes that checkable rather
    #: than merely stated.
    canonical_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_by_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    change_reason_code: Mapped[PolicyChangeReason] = mapped_column(
        enum_type(PolicyChangeReason), nullable=False
    )
    change_ticket_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AuthorizationDomainDefinition(Base, TimestampMixin):
    """§2.2.1. Which authorization domains exist in a revision, and whether
    each is usable.

    `authorization_domain_key` is a plain string, deliberately. §2.2.1 says
    the physical store must not use a closed `SCHOOL|PLATFORM` enum that would
    need existing rows rewritten to add a domain safely — so a new domain
    arrives as a row in a new revision, not as a schema change.
    """

    __tablename__ = "authorization_domain_definition"
    __table_args__ = (
        UniqueConstraint(
            "policy_revision_id",
            "authorization_domain_key",
            name="uq_authorization_domain_per_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("adm"))
    policy_revision_id: Mapped[str] = mapped_column(
        ForeignKey("authorization_policy_revision.id", ondelete="CASCADE"), nullable=False
    )
    authorization_domain_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AuthorizationDomainStatus] = mapped_column(
        enum_type(AuthorizationDomainStatus), nullable=False
    )
    owner_module_id: Mapped[str] = mapped_column(String(8), nullable=False)
    context_resolver_key: Mapped[str] = mapped_column(String(120), nullable=False)
    requires_subject_guard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: §2.2.1: always false in this revision — an Organization is not an
    #: authorization domain, and a commercial agreement creates no role.
    is_organization_contract_scope: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class PermissionDefinition(Base, TimestampMixin):
    """§2.3. One atomic right, in exactly one domain.

    The composite foreign key back to the domain is the point: a permission
    cannot name a domain from a different revision, and cannot name one that
    does not exist. An unknown, retired or wrongly scoped permission is deny.
    """

    __tablename__ = "permission_definition"
    __table_args__ = (
        UniqueConstraint(
            "policy_revision_id", "permission_key", name="uq_permission_per_revision"
        ),
        # §2.3 verbatim: "HIGH/CRITICAL je uvek `true`". Written as a CHECK
        # rather than trusted to the seed, because a registry row that claimed
        # a CRITICAL permission needs no step-up would silently disable it for
        # every caller, and nothing else in the system would notice.
        CheckConstraint(
            "risk_level NOT IN ('HIGH', 'CRITICAL') OR step_up_required",
            name="ck_permission_step_up_for_high_risk",
        ),
        ForeignKeyConstraint(
            ["policy_revision_id", "authorization_domain_key"],
            [
                "authorization_domain_definition.policy_revision_id",
                "authorization_domain_definition.authorization_domain_key",
            ],
            name="fk_permission_domain_in_revision",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("perm"))
    policy_revision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_key: Mapped[str] = mapped_column(String(120), nullable=False)
    authorization_domain_key: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(enum_type(RiskLevel), nullable=False)
    delegation_class: Mapped[DelegationClass] = mapped_column(
        enum_type(DelegationClass), nullable=False
    )
    #: §2.3: HIGH/CRITICAL is always true. A CHECK enforces it, because a
    #: registry row that says otherwise would silently drop step-up.
    step_up_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    offline_policy: Mapped[OfflinePolicy] = mapped_column(
        enum_type(OfflinePolicy), nullable=False, default=OfflinePolicy.DENY
    )
    child_data_class: Mapped[ChildDataClass] = mapped_column(
        enum_type(ChildDataClass), nullable=False, default=ChildDataClass.NONE
    )
    #: Set when the right is not sufficient without a relationship — a
    #: guardian's link to a child, an instructor's assignment to a group.
    subject_guard_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[PermissionStatus] = mapped_column(
        enum_type(PermissionStatus), nullable=False, default=PermissionStatus.ACTIVE
    )


class RoleDefinition(Base, TimestampMixin):
    """§2.4. What a role key means in a revision.

    `workspace_key` is the field M03's TEN-Q01 needs: §2.4 fixes the school
    mapping (OWNER/MANAGER/LIMITED_ADMIN→ADMIN, INSTRUCTOR/
    SUBSTITUTE_INSTRUCTOR→INSTRUCTOR, GUARDIAN→GUARDIAN, PAYER→PAYER), and
    that mapping is what turns "this person's active roles here" into "the
    workspaces they may choose between". It is a display grouping and nothing
    more — §3.1 step 5 is explicit that the chosen workspace does not filter
    effective permissions.

    `administrative_rank` orders roles for *administration* only. §3.2 point 2:
    rank inherits no permission.
    """

    __tablename__ = "role_definition"
    __table_args__ = (
        UniqueConstraint(
            "policy_revision_id",
            "authorization_domain_key",
            "role_key",
            name="uq_role_definition_per_revision",
        ),
        ForeignKeyConstraint(
            ["policy_revision_id", "authorization_domain_key"],
            [
                "authorization_domain_definition.policy_revision_id",
                "authorization_domain_definition.authorization_domain_key",
            ],
            name="fk_role_domain_in_revision",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rold"))
    policy_revision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role_key: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization_domain_key: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Null for platform roles: a platform role has no school workspace, and
    #: §2.6 keeps it free of `school_id` entirely.
    workspace_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    localization_key: Mapped[str] = mapped_column(String(120), nullable=False)
    administrative_rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    assignment_policy: Mapped[AssignmentPolicy] = mapped_column(
        enum_type(AssignmentPolicy), nullable=False
    )
    status: Mapped[RoleDefinitionStatus] = mapped_column(
        enum_type(RoleDefinitionStatus), nullable=False, default=RoleDefinitionStatus.ACTIVE
    )
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


class RolePermissionBinding(Base, TimestampMixin):
    """§2.4. One role holds one permission, in one revision.

    All three columns are the primary key, and the binding is immutable inside
    a published revision. Both foreign keys carry `policy_revision_id`, so a
    binding cannot reach across revisions to a role or permission that a later
    revision changed — the same "the key travels with the reference" idea M03
    §7.3 applies to tenants, applied here to revisions.
    """

    __tablename__ = "role_permission_binding"
    __table_args__ = (
        ForeignKeyConstraint(
            ["policy_revision_id", "authorization_domain_key", "role_key"],
            [
                "role_definition.policy_revision_id",
                "role_definition.authorization_domain_key",
                "role_definition.role_key",
            ],
            name="fk_binding_role_in_revision",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["policy_revision_id", "permission_key"],
            [
                "permission_definition.policy_revision_id",
                "permission_definition.permission_key",
            ],
            name="fk_binding_permission_in_revision",
            ondelete="CASCADE",
        ),
    )

    policy_revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    permission_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    #: Carried so the composite key to `role_definition` can name the domain.
    #: A role key is unique only within its domain (§2.4).
    authorization_domain_key: Mapped[str] = mapped_column(String(64), nullable=False)
