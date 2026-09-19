"""M05 policy revision 1.3 — the canonical content, as data (§2.2.1, §2.3, §3.3).

Transcribed from the contract's own tables, one entry per row. Nothing here is
invented: §3.3 is explicit that "Permission-i drugih modula dodaju se isključivo
objavom nove policy revizije nakon što njihov kanonski modul definiše semantiku;
programer ih ne izmišlja." A test asserts every key in this module appears in
the contract and vice versa.

This is the content of *one* revision. A published revision is immutable, so a
correction is a new revision with a new number — never an edit of this data
plus a re-run of the seed.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.authorization.enums import (
    DOMAIN_EVENT_ORGANIZER_WORKSPACE,
    DOMAIN_PLATFORM,
    DOMAIN_SCHOOL,
    DOMAIN_VENUE_OPERATOR_WORKSPACE,
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
from app.domains.authorization.models import (
    AuthorizationDomainDefinition,
    AuthorizationPolicyRevision,
    PermissionDefinition,
    RoleDefinition,
    RolePermissionBinding,
)

#: §3.3's revision. The number is the contract's, not a running counter.
REVISION_NO = 13
REVISION_LABEL = "1.3"


@dataclasses.dataclass(frozen=True, slots=True)
class DomainSpec:
    key: str
    status: AuthorizationDomainStatus
    owner_module_id: str
    context_resolver_key: str
    requires_subject_guard: bool


@dataclasses.dataclass(frozen=True, slots=True)
class RoleSpec:
    key: str
    domain: str
    workspace_key: str | None
    administrative_rank: int
    assignment_policy: AssignmentPolicy
    display_order: int


@dataclasses.dataclass(frozen=True, slots=True)
class PermissionSpec:
    key: str
    domain: str
    risk: RiskLevel
    delegation: DelegationClass
    roles: tuple[str, ...]
    child_data_class: ChildDataClass = ChildDataClass.NONE

    @property
    def step_up_required(self) -> bool:
        """§2.3: HIGH/CRITICAL is always true.

        Derived rather than transcribed, so a row cannot disagree with its own
        risk level — and the database CHECK refuses it anyway if one ever did.
        """
        return self.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    @property
    def resource_type(self) -> str:
        return self.key.rsplit(".", 1)[0]

    @property
    def action(self) -> str:
        return self.key.rsplit(".", 1)[1]


#: §2.2.1. H0 requires SCHOOL and PLATFORM ACTIVE and both future workspace
#: domains RESERVED — present so the evaluator already knows they are deny,
#: rather than treating them as unknown keys later.
DOMAINS: tuple[DomainSpec, ...] = (
    DomainSpec(DOMAIN_SCHOOL, AuthorizationDomainStatus.ACTIVE, "M03", "m03.school_context", True),
    DomainSpec(
        DOMAIN_PLATFORM, AuthorizationDomainStatus.ACTIVE, "M05", "m05.platform_context", False
    ),
    DomainSpec(
        DOMAIN_EVENT_ORGANIZER_WORKSPACE,
        AuthorizationDomainStatus.RESERVED,
        "M30",
        "m30.event_organizer_context",
        True,
    ),
    DomainSpec(
        DOMAIN_VENUE_OPERATOR_WORKSPACE,
        AuthorizationDomainStatus.RESERVED,
        "M33",
        "m33.venue_operator_context",
        True,
    ),
)

#: §2.4. Rank orders roles for *administration* only — §3.2 point 2 is explicit
#: that rank inherits no permission.
ROLES: tuple[RoleSpec, ...] = (
    RoleSpec("OWNER", DOMAIN_SCHOOL, "ADMIN", 100, AssignmentPolicy.M04_M02_ONLY, 1),
    RoleSpec("MANAGER", DOMAIN_SCHOOL, "ADMIN", 80, AssignmentPolicy.OWNER_MANAGED, 2),
    RoleSpec(
        "LIMITED_ADMIN", DOMAIN_SCHOOL, "ADMIN", 60,
        AssignmentPolicy.OWNER_OR_MANAGER_MANAGED, 3,
    ),
    RoleSpec(
        "INSTRUCTOR", DOMAIN_SCHOOL, "INSTRUCTOR", 40,
        AssignmentPolicy.OWNER_OR_MANAGER_MANAGED, 4,
    ),
    RoleSpec(
        "SUBSTITUTE_INSTRUCTOR", DOMAIN_SCHOOL, "INSTRUCTOR", 30,
        AssignmentPolicy.OWNER_OR_MANAGER_MANAGED, 5,
    ),
    RoleSpec("GUARDIAN", DOMAIN_SCHOOL, "GUARDIAN", 20, AssignmentPolicy.M07_ONLY, 6),
    RoleSpec("PAYER", DOMAIN_SCHOOL, "PAYER", 10, AssignmentPolicy.M07_ONLY, 7),
    RoleSpec(
        "PLATFORM_OPERATIONS_ADMIN", DOMAIN_PLATFORM, None, 100,
        AssignmentPolicy.PLATFORM_SECURITY_MANAGED, 1,
    ),
    RoleSpec(
        "PLATFORM_SECURITY_ADMIN", DOMAIN_PLATFORM, None, 100,
        AssignmentPolicy.PLATFORM_SECURITY_MANAGED, 2,
    ),
    RoleSpec(
        "PLATFORM_SUPPORT_AGENT", DOMAIN_PLATFORM, None, 50,
        AssignmentPolicy.PLATFORM_SECURITY_MANAGED, 3,
    ),
    RoleSpec(
        "PLATFORM_INCIDENT_COMMANDER", DOMAIN_PLATFORM, None, 50,
        AssignmentPolicy.PLATFORM_SECURITY_MANAGED, 4,
    ),
    RoleSpec(
        "PLATFORM_BILLING_ADMIN", DOMAIN_PLATFORM, None, 50,
        AssignmentPolicy.PLATFORM_SECURITY_MANAGED, 5,
    ),
)

_OWNER = ("OWNER",)
_OWNER_MANAGER = ("OWNER", "MANAGER")
_SEC = ("PLATFORM_SECURITY_ADMIN",)
_OPS = ("PLATFORM_OPERATIONS_ADMIN",)
_BILLING = ("PLATFORM_BILLING_ADMIN",)

#: §3.3's table, row for row. `delegation_class` comes from the second table
#: in the same section, which closes delegation for every M05 key.
PERMISSIONS: tuple[PermissionSpec, ...] = (
    # --- school RBAC ---
    PermissionSpec(
        "school.rbac.assignments.view", DOMAIN_SCHOOL, RiskLevel.ELEVATED,
        DelegationClass.DIRECT_DELEGABLE, _OWNER_MANAGER,
    ),
    PermissionSpec(
        "school.rbac.roles.assign", DOMAIN_SCHOOL, RiskLevel.HIGH,
        DelegationClass.ROLE_ONLY, _OWNER_MANAGER,
    ),
    PermissionSpec(
        "school.rbac.roles.suspend", DOMAIN_SCHOOL, RiskLevel.HIGH,
        DelegationClass.ROLE_ONLY, _OWNER_MANAGER,
    ),
    PermissionSpec(
        "school.rbac.roles.revoke", DOMAIN_SCHOOL, RiskLevel.HIGH,
        DelegationClass.ROLE_ONLY, _OWNER_MANAGER,
    ),
    PermissionSpec(
        "school.rbac.permissions.delegate", DOMAIN_SCHOOL, RiskLevel.CRITICAL,
        DelegationClass.DIRECT_DELEGABLE, _OWNER,
    ),
    PermissionSpec(
        "school.rbac.permissions.revoke", DOMAIN_SCHOOL, RiskLevel.CRITICAL,
        DelegationClass.DIRECT_DELEGABLE, _OWNER,
    ),
    PermissionSpec(
        "school.rbac.labels.manage", DOMAIN_SCHOOL, RiskLevel.LOW,
        DelegationClass.DIRECT_DELEGABLE, _OWNER_MANAGER,
    ),
    # --- school support ---
    PermissionSpec(
        "school.support.requests.approve", DOMAIN_SCHOOL, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OWNER,
    ),
    PermissionSpec(
        "school.support.grants.revoke", DOMAIN_SCHOOL, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OWNER,
    ),
    PermissionSpec(
        "school.support.activity.view", DOMAIN_SCHOOL, RiskLevel.HIGH,
        DelegationClass.DIRECT_DELEGABLE, _OWNER,
    ),
    # --- M04 school keys ---
    PermissionSpec(
        "school.profile.manage", DOMAIN_SCHOOL, RiskLevel.HIGH,
        DelegationClass.DIRECT_DELEGABLE, _OWNER_MANAGER,
    ),
    PermissionSpec(
        "school.lifecycle.activate", DOMAIN_SCHOOL, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OWNER,
    ),
    PermissionSpec(
        "school.owners.manage", DOMAIN_SCHOOL, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OWNER,
    ),
    PermissionSpec(
        "school.subscription_usage.view", DOMAIN_SCHOOL, RiskLevel.ELEVATED,
        DelegationClass.DIRECT_DELEGABLE, _OWNER_MANAGER,
    ),
    # --- platform: policy and accounts ---
    PermissionSpec(
        "platform.authorization.catalog.publish", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _SEC,
    ),
    PermissionSpec(
        "platform.notification.policy.publish", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _SEC,
    ),
    PermissionSpec(
        "platform.roles.manage", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _SEC,
    ),
    PermissionSpec(
        "platform.accounts.suspend", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _SEC,
    ),
    PermissionSpec(
        "platform.accounts.reactivate", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _SEC,
    ),
    PermissionSpec(
        "platform.accounts.disable", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _SEC,
    ),
    # --- platform: M04 operations ---
    PermissionSpec(
        "platform.organizations.manage", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OPS,
    ),
    PermissionSpec(
        "platform.schools.create", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OPS,
    ),
    PermissionSpec(
        "platform.schools.lifecycle.manage", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OPS,
    ),
    PermissionSpec(
        "platform.schools.ownership.manage", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OPS,
    ),
    PermissionSpec(
        "platform.school_ownership.override", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OPS,
    ),
    PermissionSpec(
        "platform.product_entitlements.manage", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _OPS,
    ),
    # --- platform: billing ---
    PermissionSpec(
        "platform.billing_administration", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _BILLING,
    ),
    # --- platform: support ---
    PermissionSpec(
        "platform.support.requests.create", DOMAIN_PLATFORM, RiskLevel.ELEVATED,
        DelegationClass.ROLE_ONLY, ("PLATFORM_SUPPORT_AGENT",),
    ),
    PermissionSpec(
        "platform.support.sessions.start", DOMAIN_PLATFORM, RiskLevel.HIGH,
        DelegationClass.ROLE_ONLY, ("PLATFORM_SUPPORT_AGENT",),
    ),
    PermissionSpec(
        "platform.support.break_glass.activate", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, ("PLATFORM_INCIDENT_COMMANDER",),
    ),
    PermissionSpec(
        "platform.support.break_glass.ratify", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _SEC,
    ),
    PermissionSpec(
        "platform.support.reviews.complete", DOMAIN_PLATFORM, RiskLevel.HIGH,
        DelegationClass.ROLE_ONLY, _SEC,
    ),
    # --- platform: commercial (§3.3: PLATFORM_BILLING_ADMIN only, no delegate path) ---
    PermissionSpec(
        "platform.commercial.catalog.manage", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _BILLING,
    ),
    PermissionSpec(
        "platform.commercial.plans.manage", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _BILLING,
    ),
    PermissionSpec(
        "platform.commercial.agreements.manage", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _BILLING,
    ),
    PermissionSpec(
        "platform.commercial.agreements.acceptance.record", DOMAIN_PLATFORM,
        RiskLevel.CRITICAL, DelegationClass.ROLE_ONLY, _BILLING,
    ),
    PermissionSpec(
        "platform.commercial.adjustments.manage", DOMAIN_PLATFORM, RiskLevel.CRITICAL,
        DelegationClass.ROLE_ONLY, _BILLING,
    ),
    PermissionSpec(
        "platform.commercial.read", DOMAIN_PLATFORM, RiskLevel.ELEVATED,
        DelegationClass.ROLE_ONLY, _BILLING,
    ),
)


def canonical_hash() -> str:
    """§2.2's `canonical_content_hash`, over a stable serialization.

    Sorted at every level so the hash depends on the *content* and not on the
    order this module happens to list it in. It is what makes "a published
    revision is immutable" checkable rather than merely asserted: change a
    binding and the stored hash stops matching what the code would compute.
    """
    content = {
        "revision": REVISION_LABEL,
        "domains": sorted(
            [d.key, d.status.value, d.owner_module_id, d.context_resolver_key,
             d.requires_subject_guard]
            for d in DOMAINS
        ),
        "roles": sorted(
            [r.key, r.domain, r.workspace_key or "", r.administrative_rank,
             r.assignment_policy.value]
            for r in ROLES
        ),
        "permissions": sorted(
            [p.key, p.domain, p.risk.value, p.delegation.value, p.step_up_required]
            for p in PERMISSIONS
        ),
        "bindings": sorted(
            [p.key, role] for p in PERMISSIONS for role in p.roles
        ),
    }
    payload = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_policy_revision(db: Session) -> AuthorizationPolicyRevision:
    """Publish revision 1.3 if it is not already there, and leave it alone if
    it is.

    Idempotent on `revision_no`. A published revision is immutable (§2.2), so
    this never updates one it finds — if the stored hash disagrees with what
    this module would compute, that is a fact to surface, not to overwrite,
    and the test suite is where it surfaces.
    """
    existing = db.execute(
        select(AuthorizationPolicyRevision).where(
            AuthorizationPolicyRevision.revision_no == REVISION_NO
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    revision = AuthorizationPolicyRevision(
        revision_no=REVISION_NO,
        status=PolicyRevisionStatus.ACTIVE,
        canonical_content_hash=canonical_hash(),
        change_reason_code=PolicyChangeReason.INITIAL_PUBLICATION,
        change_ticket_ref=f"M05-REGISTRY-{REVISION_LABEL}",
    )
    db.add(revision)
    db.flush()

    for domain in DOMAINS:
        db.add(
            AuthorizationDomainDefinition(
                policy_revision_id=revision.id,
                authorization_domain_key=domain.key,
                status=domain.status,
                owner_module_id=domain.owner_module_id,
                context_resolver_key=domain.context_resolver_key,
                requires_subject_guard=domain.requires_subject_guard,
                is_organization_contract_scope=False,
            )
        )
    db.flush()

    for role in ROLES:
        db.add(
            RoleDefinition(
                policy_revision_id=revision.id,
                role_key=role.key,
                authorization_domain_key=role.domain,
                workspace_key=role.workspace_key,
                localization_key=f"role.{role.key.lower()}",
                administrative_rank=role.administrative_rank,
                assignment_policy=role.assignment_policy,
                status=RoleDefinitionStatus.ACTIVE,
                display_order=role.display_order,
            )
        )
    for permission in PERMISSIONS:
        db.add(
            PermissionDefinition(
                policy_revision_id=revision.id,
                permission_key=permission.key,
                authorization_domain_key=permission.domain,
                resource_type=permission.resource_type,
                action=permission.action,
                risk_level=permission.risk,
                delegation_class=permission.delegation,
                step_up_required=permission.step_up_required,
                offline_policy=OfflinePolicy.DENY,
                child_data_class=permission.child_data_class,
                status=PermissionStatus.ACTIVE,
            )
        )
    db.flush()

    for permission in PERMISSIONS:
        for role_key in permission.roles:
            db.add(
                RolePermissionBinding(
                    policy_revision_id=revision.id,
                    role_key=role_key,
                    permission_key=permission.key,
                    authorization_domain_key=permission.domain,
                )
            )
    db.flush()
    return revision
