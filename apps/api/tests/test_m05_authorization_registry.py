"""M05 §2.2–2.4: the authorization policy registry's shape.

This slice adds the tables and nothing that reads them — seeding revision 1.3
and the resolver come next. So what is worth testing is exactly the part that
a later seed cannot fix if it is wrong: the invariants the database itself
holds.

Two of them matter more than the rest, because both are the kind that survive
in application code only until somebody writes a second code path:

* exactly one revision may be `ACTIVE` (§2.2);
* a `HIGH` or `CRITICAL` permission always requires step-up (§2.3).
"""

from __future__ import annotations

import pytest
from app.domains.authorization.enums import (
    DOMAIN_PLATFORM,
    DOMAIN_SCHOOL,
    AssignmentPolicy,
    AuthorizationDomainStatus,
    DelegationClass,
    PolicyChangeReason,
    PolicyRevisionStatus,
    RiskLevel,
)
from app.domains.authorization.models import (
    AuthorizationDomainDefinition,
    AuthorizationPolicyRevision,
    PermissionDefinition,
    RoleDefinition,
    RolePermissionBinding,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _revision(
    db: Session,
    *,
    no: int,
    status: PolicyRevisionStatus = PolicyRevisionStatus.DRAFT,
) -> AuthorizationPolicyRevision:
    revision = AuthorizationPolicyRevision(
        revision_no=no,
        status=status,
        canonical_content_hash=f"{no:064d}",
        change_reason_code=PolicyChangeReason.INITIAL_PUBLICATION,
        change_ticket_ref=f"TICKET-{no}",
    )
    db.add(revision)
    db.flush()
    return revision


def _domain(
    db: Session,
    revision: AuthorizationPolicyRevision,
    *,
    key: str = DOMAIN_SCHOOL,
    status: AuthorizationDomainStatus = AuthorizationDomainStatus.ACTIVE,
) -> AuthorizationDomainDefinition:
    domain = AuthorizationDomainDefinition(
        policy_revision_id=revision.id,
        authorization_domain_key=key,
        status=status,
        owner_module_id="M03" if key == DOMAIN_SCHOOL else "M05",
        context_resolver_key=f"resolver.{key.lower()}",
        requires_subject_guard=key == DOMAIN_SCHOOL,
    )
    db.add(domain)
    db.flush()
    return domain


# ---------------------------------------------------------------------------
# §2.2 — exactly one ACTIVE revision
# ---------------------------------------------------------------------------


def test_only_one_revision_can_be_active(db: Session) -> None:
    """The invariant the whole registry rests on. Two ACTIVE revisions would
    mean two answers to "what may this role do", and whichever the query
    happened to read would win.

    The seeded revision 1.3 is already the active one — so this adds a second
    against a registry in its real shape, rather than one arranged for the
    test.
    """
    assert db.execute(
        text(
            "SELECT count(*) FROM authorization_policy_revision"
            " WHERE status = 'ACTIVE'"
        )
    ).scalar_one() == 1

    # The helper flushes, so the raise has to wrap the call itself — wrapping a
    # later `db.flush()` would be asserting against a statement that never runs.
    with pytest.raises(IntegrityError):
        _revision(db, no=2, status=PolicyRevisionStatus.ACTIVE)
    db.rollback()


def test_many_revisions_may_be_draft_or_superseded(db: Session) -> None:
    """The index is partial on purpose: history is the point. A superseded
    revision is how "what did this role mean in March" stays answerable."""
    _revision(db, no=2, status=PolicyRevisionStatus.SUPERSEDED)
    _revision(db, no=3, status=PolicyRevisionStatus.SUPERSEDED)
    _revision(db, no=4, status=PolicyRevisionStatus.DRAFT)
    _revision(db, no=5, status=PolicyRevisionStatus.DRAFT)
    db.commit()

    # Four added, plus the seeded active one.
    assert db.execute(
        text("SELECT count(*) FROM authorization_policy_revision")
    ).scalar_one() == 5


def test_revision_numbers_are_unique(db: Session) -> None:
    _revision(db, no=7)
    db.flush()
    with pytest.raises(IntegrityError):
        _revision(db, no=7)
    db.rollback()


# ---------------------------------------------------------------------------
# §2.3 — step-up is not optional for high risk
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("risk", [RiskLevel.HIGH, RiskLevel.CRITICAL])
def test_high_risk_permission_must_require_step_up(
    db: Session, risk: RiskLevel
) -> None:
    """§2.3 verbatim: "HIGH/CRITICAL je uvek `true`".

    A registry row claiming otherwise would silently disable step-up for every
    caller of that permission, and nothing else in the system would notice —
    which is why it is a CHECK and not a convention.
    """
    revision = _revision(db, no=1)
    _domain(db, revision)
    db.add(
        PermissionDefinition(
            policy_revision_id=revision.id,
            permission_key="school.rbac.roles.assign",
            authorization_domain_key=DOMAIN_SCHOOL,
            resource_type="role_assignment",
            action="assign",
            risk_level=risk,
            delegation_class=DelegationClass.ROLE_ONLY,
            step_up_required=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


@pytest.mark.parametrize("risk", [RiskLevel.LOW, RiskLevel.ELEVATED])
def test_lower_risk_permission_may_skip_step_up(db: Session, risk: RiskLevel) -> None:
    """The constraint must refuse the wrong thing without refusing the right
    one: a LOW-risk read is exactly what step-up should not interrupt."""
    revision = _revision(db, no=1)
    _domain(db, revision)
    db.add(
        PermissionDefinition(
            policy_revision_id=revision.id,
            permission_key="school.rbac.assignments.view",
            authorization_domain_key=DOMAIN_SCHOOL,
            resource_type="role_assignment",
            action="view",
            risk_level=risk,
            delegation_class=DelegationClass.DIRECT_DELEGABLE,
            step_up_required=False,
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# The revision travels with every reference
# ---------------------------------------------------------------------------


def test_a_permission_cannot_name_a_domain_from_another_revision(
    db: Session,
) -> None:
    """The same idea M03 §7.3 applies to tenants, applied to revisions: the
    key travels *inside* the reference, so a row cannot reach across a
    revision boundary into a definition a later publication changed."""
    first = _revision(db, no=1)
    second = _revision(db, no=2)
    _domain(db, first)
    db.commit()

    db.add(
        PermissionDefinition(
            policy_revision_id=second.id,  # no SCHOOL domain in revision 2
            permission_key="school.rbac.assignments.view",
            authorization_domain_key=DOMAIN_SCHOOL,
            resource_type="role_assignment",
            action="view",
            risk_level=RiskLevel.ELEVATED,
            delegation_class=DelegationClass.DIRECT_DELEGABLE,
            step_up_required=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_binding_cannot_name_a_permission_from_another_revision(
    db: Session,
) -> None:
    first = _revision(db, no=1)
    second = _revision(db, no=2)
    _domain(db, first)
    _domain(db, second)
    db.add_all([
        PermissionDefinition(
            policy_revision_id=first.id,
            permission_key="school.rbac.assignments.view",
            authorization_domain_key=DOMAIN_SCHOOL,
            resource_type="role_assignment",
            action="view",
            risk_level=RiskLevel.ELEVATED,
            delegation_class=DelegationClass.DIRECT_DELEGABLE,
            step_up_required=False,
        ),
        RoleDefinition(
            policy_revision_id=second.id,
            role_key="OWNER",
            authorization_domain_key=DOMAIN_SCHOOL,
            workspace_key="ADMIN",
            localization_key="role.owner",
            administrative_rank=100,
            assignment_policy=AssignmentPolicy.M04_M02_ONLY,
        ),
    ])
    db.commit()

    # Revision 2's OWNER, revision 1's permission.
    db.add(
        RolePermissionBinding(
            policy_revision_id=second.id,
            role_key="OWNER",
            permission_key="school.rbac.assignments.view",
            authorization_domain_key=DOMAIN_SCHOOL,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ---------------------------------------------------------------------------
# §2.2.1 and §2.4 — shape
# ---------------------------------------------------------------------------


def test_the_domain_key_is_not_a_database_enum(db: Session) -> None:
    """§2.2.1 forbids a closed `SCHOOL|PLATFORM` enum that would need existing
    rows rewritten to add a domain safely. A future workspace domain has to be
    insertable as a row in a new revision — so this proves an unknown key is
    accepted by the *column*, while remaining deny at the policy level because
    its status is not ACTIVE."""
    revision = _revision(db, no=2)
    _domain(
        db,
        revision,
        key="EVENT_ORGANIZER_WORKSPACE",
        status=AuthorizationDomainStatus.RESERVED,
    )
    db.commit()

    # Scoped to this revision: the seeded 1.3 already carries the same key, and
    # an unscoped query would find both.
    status = db.execute(
        text(
            "SELECT status FROM authorization_domain_definition"
            " WHERE authorization_domain_key = 'EVENT_ORGANIZER_WORKSPACE'"
            "   AND policy_revision_id = :rev"
        ),
        {"rev": revision.id},
    ).scalar_one()
    assert status == AuthorizationDomainStatus.RESERVED.value


def test_a_platform_role_has_no_workspace(db: Session) -> None:
    """§2.4: workspace is a school display grouping. A platform role has no
    school, so it has no workspace — and §2.6 keeps `school_id` off it
    entirely."""
    revision = _revision(db, no=1)
    _domain(db, revision, key=DOMAIN_PLATFORM)
    db.add(
        RoleDefinition(
            policy_revision_id=revision.id,
            role_key="PLATFORM_SECURITY_ADMIN",
            authorization_domain_key=DOMAIN_PLATFORM,
            workspace_key=None,
            localization_key="role.platform_security_admin",
            administrative_rank=100,
            assignment_policy=AssignmentPolicy.PLATFORM_SECURITY_MANAGED,
        )
    )
    db.commit()


def test_the_registry_has_no_tenant_column(db: Session) -> None:
    """Reference data, not tenant data. A `school_id` here would invite
    per-school policy, which §3.2 point 3 rules out: a new permission is
    default-deny for every role until a published revision says otherwise."""
    tenanted = db.execute(
        text(
            "SELECT table_name FROM information_schema.columns"
            " WHERE column_name = 'school_id'"
            " AND table_name IN ('authorization_policy_revision',"
            "  'authorization_domain_definition', 'permission_definition',"
            "  'role_definition', 'role_permission_binding')"
        )
    ).scalars().all()
    assert tenanted == []
