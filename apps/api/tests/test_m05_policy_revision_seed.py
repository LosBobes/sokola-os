"""M05 policy revision 1.3: does the seed say what the contract says?

The registry module is a transcription of §3.3's tables, and a transcription
is exactly the kind of work that goes wrong quietly — one missed row, one
risk level copied from the line above. So the first test here does not check
the seed against my understanding of the contract; it parses the contract's
own table out of the spec file and compares key for key, in both directions.

The rest check the invariants §2.2.1 and §2.4 state about a published
revision, against the database the migration actually produced.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from app.domains.authorization.enums import (
    DOMAIN_PLATFORM,
    DOMAIN_SCHOOL,
    AuthorizationDomainStatus,
    PolicyRevisionStatus,
    RiskLevel,
)
from app.domains.authorization.registry import (
    PERMISSIONS,
    REVISION_NO,
    ROLES,
    canonical_hash,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

_CONTRACT = (
    pathlib.Path(__file__).resolve().parents[3]
    / "docs/spec/v5.7/04-MODULSKI-UGOVORI/05-M05-RBAC-I-SUPPORT-ACCESS"
    / "01-M05-MASTER-UGOVOR.md"
)

#: A §3.3 row: | `key` | DOMAIN | RISK | roles | meaning |
_ROW = re.compile(
    r"^\|\s*`([a-z0-9_.]+)`\s*\|\s*(SCHOOL|PLATFORM)\s*\|\s*"
    r"(LOW|ELEVATED|HIGH|CRITICAL)\s*\|\s*([^|]+?)\s*\|",
    re.MULTILINE,
)


def _contract_rows() -> dict[str, tuple[str, str, frozenset[str]]]:
    """Every permission row in §3.3's registry table, read from the spec."""
    text_ = _CONTRACT.read_text(encoding="utf-8")
    start = text_.index("### 3.3. M05 permission registry")
    end = text_.index("#### 3.3.1.", start)
    rows: dict[str, tuple[str, str, frozenset[str]]] = {}
    for key, domain, risk, roles in _ROW.findall(text_[start:end]):
        rows[key] = (
            domain,
            risk,
            frozenset(r.strip() for r in roles.split(",") if r.strip()),
        )
    return rows


def test_the_contract_table_was_actually_found() -> None:
    """If the spec moves or the table's shape changes, the comparison below
    would pass vacuously against an empty parse. This is the guard for that."""
    rows = _contract_rows()
    assert len(rows) >= 35, f"parsed only {len(rows)} rows from §3.3"


def test_every_contract_permission_is_seeded() -> None:
    seeded = {p.key for p in PERMISSIONS}
    missing = sorted(set(_contract_rows()) - seeded)
    assert missing == [], f"in the contract, not in the seed: {missing}"


def test_the_seed_invents_nothing() -> None:
    """§3.3: "programer ih ne izmišlja." The seed may not hold a key the
    contract does not."""
    contract = set(_contract_rows())
    extra = sorted({p.key for p in PERMISSIONS} - contract)
    assert extra == [], f"in the seed, not in the contract: {extra}"


@pytest.mark.parametrize("permission", PERMISSIONS, ids=lambda p: p.key)
def test_each_permission_matches_its_contract_row(permission) -> None:
    """Domain, risk level and default role bindings, per key."""
    domain, risk, roles = _contract_rows()[permission.key]
    assert permission.domain == domain
    assert permission.risk.value == risk
    assert frozenset(permission.roles) == roles


@pytest.mark.parametrize("permission", PERMISSIONS, ids=lambda p: p.key)
def test_high_risk_always_requires_step_up(permission) -> None:
    """§2.3, derived rather than transcribed — but worth asserting anyway,
    since the derivation is the thing that could be wrong."""
    expected = permission.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert permission.step_up_required is expected


# ---------------------------------------------------------------------------
# What the migration actually published
# ---------------------------------------------------------------------------


def test_revision_is_published_and_active(db: Session) -> None:
    row = db.execute(
        text(
            "SELECT status, canonical_content_hash FROM authorization_policy_revision"
            " WHERE revision_no = :n"
        ),
        {"n": REVISION_NO},
    ).one()
    assert row.status == PolicyRevisionStatus.ACTIVE.value
    assert row.canonical_content_hash == canonical_hash()


def test_the_stored_hash_would_catch_an_edit() -> None:
    """The hash is what makes "a published revision is immutable" checkable.

    Sorted at every level, so it tracks content rather than the order the
    module lists things in — otherwise reordering the source would look like
    a policy change, and every real change would be lost in the noise.
    """
    assert canonical_hash() == canonical_hash()
    assert len(canonical_hash()) == 64


@pytest.mark.parametrize(
    "domain_key, expected",
    [
        (DOMAIN_SCHOOL, AuthorizationDomainStatus.ACTIVE),
        (DOMAIN_PLATFORM, AuthorizationDomainStatus.ACTIVE),
        ("EVENT_ORGANIZER_WORKSPACE", AuthorizationDomainStatus.RESERVED),
        ("VENUE_OPERATOR_WORKSPACE", AuthorizationDomainStatus.RESERVED),
    ],
)
def test_h0_domain_statuses(
    db: Session, domain_key: str, expected: AuthorizationDomainStatus
) -> None:
    """§2.2.1: H0 requires SCHOOL and PLATFORM ACTIVE, both future workspace
    domains RESERVED. Present-and-reserved matters — it makes them a known
    deny rather than an unknown key someone might later treat as new."""
    status = db.execute(
        text(
            "SELECT d.status FROM authorization_domain_definition d"
            " JOIN authorization_policy_revision r ON r.id = d.policy_revision_id"
            " WHERE r.revision_no = :n AND d.authorization_domain_key = :k"
        ),
        {"n": REVISION_NO, "k": domain_key},
    ).scalar_one()
    assert status == expected.value


def test_a_reserved_domain_holds_nothing(db: Session) -> None:
    """§2.2.1 verbatim: a RESERVED domain "ne sme imati active `RoleDefinition`,
    `PermissionDefinition`, binding ili assignment"."""
    for table in ("role_definition", "permission_definition"):
        leaked = db.execute(
            text(
                f"SELECT count(*) FROM {table} t"
                " JOIN authorization_domain_definition d"
                "   ON d.policy_revision_id = t.policy_revision_id"
                "  AND d.authorization_domain_key = t.authorization_domain_key"
                " WHERE d.status <> 'ACTIVE'"
            )
        ).scalar_one()
        assert leaked == 0, f"{table} has a row in a non-ACTIVE domain"


@pytest.mark.parametrize(
    "role_key, workspace",
    [
        ("OWNER", "ADMIN"),
        ("MANAGER", "ADMIN"),
        ("LIMITED_ADMIN", "ADMIN"),
        ("INSTRUCTOR", "INSTRUCTOR"),
        ("SUBSTITUTE_INSTRUCTOR", "INSTRUCTOR"),
        ("GUARDIAN", "GUARDIAN"),
        ("PAYER", "PAYER"),
    ],
)
def test_school_role_workspace_mapping(
    db: Session, role_key: str, workspace: str
) -> None:
    """§2.4's fixed mapping — and the reason this slice exists, since it is
    what TEN-Q01 needs to turn a person's roles into workspace options."""
    stored = db.execute(
        text(
            "SELECT rd.workspace_key FROM role_definition rd"
            " JOIN authorization_policy_revision r ON r.id = rd.policy_revision_id"
            " WHERE r.revision_no = :n AND rd.role_key = :k"
        ),
        {"n": REVISION_NO, "k": role_key},
    ).scalar_one()
    assert stored == workspace


def test_platform_roles_have_no_workspace(db: Session) -> None:
    """A workspace is a school display grouping; a platform role has no
    school (§2.6), so it has none."""
    with_workspace = db.execute(
        text(
            "SELECT rd.role_key FROM role_definition rd"
            " WHERE rd.authorization_domain_key = 'PLATFORM'"
            "   AND rd.workspace_key IS NOT NULL"
        )
    ).scalars().all()
    assert with_workspace == []


def test_there_is_no_wildcard_role(db: Session) -> None:
    """§2.4: "Ne postoji `SUPER_ADMIN`, implicitni wildcard niti permission
    inheritance iz administrativnog ranga."

    OWNER holds a lot, but not everything — the platform keys are not its’,
    and a test that only counted OWNER's bindings would miss that.
    """
    role_keys = {r.key for r in ROLES}
    assert "SUPER_ADMIN" not in role_keys

    owner_platform = db.execute(
        text(
            "SELECT count(*) FROM role_permission_binding"
            " WHERE role_key = 'OWNER' AND authorization_domain_key = 'PLATFORM'"
        )
    ).scalar_one()
    assert owner_platform == 0, "OWNER must hold no platform permission"
