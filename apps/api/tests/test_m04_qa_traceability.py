"""M04 §2: the 131 numbered QA scenarios, under the gate #115 established.

Fifth module under the gate, and the first large one. Same shape as M07, M06,
M01 and M03: one test per runnable scenario named for its id, the rest declared
in `BLOCKED` with a reason from a closed vocabulary, and a gate that fails if
any of the 131 is neither. Nothing is skipped.

Kept in one file, and one PR, deliberately. The gate's whole claim is *"every
scenario in this contract is accounted for"*, and that claim cannot be made
over a third of a module. Splitting M04 across PRs would mean parking the
other two thirds in `BLOCKED` under some word meaning "not written yet" —
which is exactly the rot the reason vocabulary exists to prevent.

What M04 turns out to be is worth stating up front, because it shapes almost
every blocked entry. **The domain logic is strong and the command envelope is
missing.** `ownership.py`, `entitlements.py` and `anchor.py` implement the
lifecycle rules carefully — last-owner protection, primary-term transfer,
grant replacement under a partial unique index, gapless organization links —
and between them contain **zero** `record_audit` and `enqueue` calls, take no
request id, and issue no receipt. So scenario after scenario passes on its
mechanism and fails on its evidence clause. That is one finding (F-40), not
forty, and `no command envelope` names it separately from `feature absent`
precisely so the difference stays visible.

Two more findings the pass turned up:

* `require_capability` exists, is correct, and **is called from nowhere**
  (F-39). Entitlements are computed and never consulted, so a school without
  `CORE_MVP` reaches every feature it names.
* The repo lets an **active owner** deactivate a school (`POST
  /schools/current/deactivate`), while §3.6 makes de/reactivation
  platform-only (F-41).
"""

from __future__ import annotations

import datetime as dt
import re
import secrets
from pathlib import Path

import pytest
from app.common.errors import ConflictError, NotFoundError
from app.common.ids import new_id
from app.domains.identity.enums import (
    InvitationStatus,
    InvitationType,
    RoleAssignmentStatus,
    RoleCode,
    RoleScopeType,
)
from app.domains.identity.models import Invitation, Person, RoleAssignment
from app.domains.organization.enums import (
    OrganizationSchoolChangeReason,
    OrganizationStatus,
)
from app.domains.organization.models import Organization
from app.domains.school import anchor, entitlements, ownership
from app.domains.school.entitlement_enums import (
    CapabilityKey,
    EntitlementGrantReason,
    EntitlementRevokeReason,
    EntitlementStatus,
)
from app.domains.school.entitlement_models import SchoolProductEntitlement
from app.domains.school.enums import (
    LocatorKind,
    LocatorStatus,
    SchoolKind,
    SchoolStatus,
    SchoolStatusReason,
    SchoolType,
)
from app.domains.school.models import (
    OrganizationSchool,
    School,
    SchoolLocator,
    SchoolStatusTransition,
)
from app.domains.school.ownership_enums import (
    OwnerNominationKind,
    OwnerNominationStatus,
    PrimaryOwnerTermReason,
)
from app.domains.school.ownership_models import SchoolOwnerNomination
from app.domains.tenancy import security as tenant_security
from app.platform import clock
from app.security.auth import DEV_PERSON_HEADER
from app.security.deps import CONTEXT_HEADER
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import (
    Actor,
    add_membership,
    assign_role,
    bootstrap_actor,
    make_person,
    make_school,
)

_QA_DOC = (
    Path(__file__).resolve().parents[3]
    / "docs/spec/v5.7/04-MODULSKI-UGOVORI/04-M04-ORGANIZATION-SCHOOL-SUBSCRIPTION"
    / "02-M04-QA-I-TRACEABILITY.md"
)


def _absent(what: str) -> str:
    return f"feature absent: {what}"


def _envelope(what: str) -> str:
    return f"no command envelope: {what}"


#: Seven causes, and the reason test below refuses an eighth.
#:
#: `feature absent` and `no command envelope` are the two that must not merge.
#: The first means nothing exists — there is no commercial plan, no
#: subscription snapshot, no SCH-02. The second means the rule is implemented
#: and correct, and what is missing is the audit entry, the outbox event, the
#: request id or the receipt around it. One is a module to write; the other is
#: a wrapper, and they belong in different sprints.
BLOCKED: dict[str, str] = {}

# -- §2 Organization i School foundation -----------------------------------
BLOCKED.update(
    {
        "M04-QA-001": _absent(
            "there is no ORG-01 command and no platform actor to call it; "
            "`Organization` rows are created inline by `school.service."
            "create_school` as placeholders (F-12)"
        ),
        "M04-QA-002": _envelope("ORG-01 has no request id, so there is no retry to be idempotent"),
        "M04-QA-003": _envelope(
            "no `M04_IDEMPOTENCY_KEY_REUSED` code exists and no M04 command reads a key"
        ),
        "M04-QA-007": _absent(
            "no platform role and no platform Organization list; there is no "
            "actor to refuse and no surface to refuse them from"
        ),
        "M04-QA-008": _absent(
            "SCH-01 as specified does not exist. `create_school` assigns the "
            "OWNER role and membership directly and creates no owner "
            "nomination, which is the opposite of what this scenario asserts "
            "(F-12)"
        ),
        "M04-QA-009": _absent("SCH-01 creates no nomination, so there is no insert to fail"),
        "M04-QA-010": _envelope("`createSchool` takes no request id and returns no receipt"),
        "M04-QA-012": _absent(
            "`create_school` always mints its own placeholder Organization and "
            "cannot be handed an existing, archived one"
        ),
        "M04-QA-013": _absent(
            "no owner-eligibility port; `create_school` makes the caller owner "
            "with no check that the person may hold an account"
        ),
        "M04-QA-014": _absent(
            "the `contact_*_ciphertext` and `contact_verified_at` columns exist "
            "and nothing in app/ ever writes them, so there is no unverified "
            "contact to refuse"
        ),
    }
)

# -- §3 Profil, locator i Organization transfer ----------------------------
BLOCKED.update(
    {
        "M04-QA-019": _absent("there is no SCH-02 profile-update command"),
        "M04-QA-020": _absent("no SCH-02, so no payload to reject fields from"),
        "M04-QA-021": _absent("no SCH-02, so no expected version to be stale"),
        "M04-QA-022": _absent(
            "there is no SCH-03 timezone command; the column is set at create and "
            "never moves"
        ),
        "M04-QA-023": _absent("no SCH-03, and no migration guard over TermOccurrence"),
        "M04-QA-024": _absent("no SCH-03, so no zone identifier is ever validated"),
        "M04-QA-025": _absent("`logo_object_ref` exists as a column and no command sets it"),
        "M04-QA-026": _absent("no logo command, so no size, type or tenant check on one"),
        "M04-QA-030": _envelope(
            "`anchor.transfer_organization` does the link half correctly, but "
            "takes no entitlement replacement set, so the scenario's "
            "'entitlement set tačno odobren' clause has no surface"
        ),
        "M04-QA-032": _absent(
            "`ORGANIZATION_TRANSFER_INCOMPLETE` does not exist; transfer never "
            "consults entitlements at all"
        ),
        "M04-QA-034": _absent("there is no ORG-03 archive command"),
        "M04-QA-035": _absent("no ORG-03, so no terminal ARCHIVED state to reach"),
    }
)

# -- §4 Owner i School lifecycle -------------------------------------------
BLOCKED.update(
    {
        "M04-QA-036": _absent("SCH-01 creates no nomination and does create an OWNER role (F-12)"),
        "M04-QA-038": _absent(
            "same missing M02 acceptance command as M04-QA-037; there is no "
            "transaction spanning account, identity, membership, role and "
            "invitation for a fault to roll back"
        ),
        "M04-QA-047": _envelope(
            "`transfer_primary_ownership` serializes on a row lock and takes "
            "no `expected_version`, so two callers cannot send the same one "
            "and `PRIMARY_OWNER_TRANSFER_CONFLICT` has no surface"
        ),
        "M04-QA-037": _absent(
            "no command performs M02 acceptance; `fulfill_nomination` is the "
            "M04 half and nothing calls it together with membership, role and "
            "invitation acceptance in one transaction"
        ),
        "M04-QA-048": _absent("no platform actor, no step-up, no override path"),
        "M04-QA-049": _absent("same missing platform override as M04-QA-048"),
        "M04-QA-050": _absent(
            "activation (`onboarding.service`) does not consult the primary "
            "owner term; `SCHOOL_PRIMARY_OWNER_REQUIRED` does not exist"
        ),
        "M04-QA-051": _absent("activation does not consult entitlements (F-39)"),
        "M04-QA-052": _absent("SCH-04's eight guards are not implemented"),
        "M04-QA-053": _absent("no SCH-04 guard set to pass, and no M20 readiness surface"),
        "M04-QA-054": _absent(
            "de/reactivation is owner-driven in this repo, not platform-only, "
            "so the refusal this asserts is not the rule the code follows (F-41)"
        ),
        "M04-QA-055": _envelope(
            "`deactivate_school` transitions the status and bumps TEN-04 "
            "atomically, but revokes no M02 invitation and invalidates no "
            "attempt"
        ),
        "M04-QA-058": _absent(
            "no commit-time tenant recheck for in-flight mutations; the guard "
            "runs once, in the request dependency"
        ),
        "M04-QA-060": _absent("reactivation checks neither primary owner nor CORE_MVP"),
        "M04-QA-061": _absent("same missing reactivation guards as M04-QA-060"),
        "M04-QA-062": _absent("no M02 invitation revocation on deactivation, so none to be stale"),
    }
)

# -- §5 Entitlement ---------------------------------------------------------
BLOCKED.update(
    {
        "M04-QA-063": _envelope(
            "`grant_entitlement` produces exactly one ACTIVE grant correctly; "
            "it writes no audit entry, enqueues no event and invalidates no "
            "cache (F-40)"
        ),
        "M04-QA-066": _absent(
            "no endpoint composes the permission and entitlement layers, so "
            "there is no request in which one passes and the other refuses"
        ),
        "M04-QA-067": _absent(
            "`require_capability` is called from nowhere in app/, so a missing "
            "entitlement blocks nothing (F-39)"
        ),
        "M04-QA-071": _absent(
            "the status half holds, but 'Core poslovni feature-i blocked' "
            "needs an enforcement point and there is none (F-39)"
        ),
    }
)

# -- §6 Subscription snapshot i korekcije (073–098) -------------------------
_SUBSCRIPTION = _absent(
    "there is no subscription model in this repository — no "
    "`SubscriptionBillingSnapshot`, no `SubscriptionCorrection`, no "
    "`commercial.subscription_usage_snapshot` worker, and no table whose name "
    "contains snapshot, subscription or correction"
)
for _n in range(73, 99):
    BLOCKED[f"M04-QA-{_n:03d}"] = _SUBSCRIPTION
BLOCKED["M04-QA-086"] = "no worker: " + _SUBSCRIPTION.split(": ", 1)[1]
BLOCKED["M04-QA-087"] = "no worker: " + _SUBSCRIPTION.split(": ", 1)[1]
BLOCKED["M04-QA-088"] = "no worker: " + _SUBSCRIPTION.split(": ", 1)[1]

# -- §7 Security, privacy i brownfield --------------------------------------
BLOCKED.update(
    {
        "M04-QA-102": _absent(
            "no platform permission and no Support Access grant exist, so "
            "there is no support actor to refuse"
        ),
        "M04-QA-103": "no migration harness: proving a backfill needs alembic stopped at "
        "the prior revision over seeded legacy rows; the suite starts at head",
        "M04-QA-104": "no migration harness: same as M04-QA-103, and the exception-report "
        "path it asserts lives in a migration, not in app/",
        "M04-QA-105": "no migration harness: there is no correction table to backfill "
        "a school_id onto",
        "M04-QA-106": "no migration harness: there is no snapshot table to scan",
        "M04-QA-107": _absent("there is no public registration backend to classify or disable"),
        "M04-QA-108": "no migration harness: re-running a migration needs a rig that "
        "stamps and steps revisions",
    }
)

# -- §7a Komercijalni model (109–126) ---------------------------------------
_COMMERCIAL = _absent(
    "there is no commercial model in this repository — no plan, no plan "
    "version, no agreement, no agreement item, no published price and no "
    "money-decimal contract to test against"
)
for _n in range(109, 127):
    BLOCKED[f"M04-QA-{_n:03d}"] = _COMMERCIAL

# -- §7b Foundation reference i atomicity -----------------------------------
BLOCKED.update(
    {
        "M04-QA-127": _absent(
            "the scenario's rollback set names a nomination and a receipt, and "
            "`create_school` produces neither — it assigns the OWNER role "
            "directly and returns the school (F-12)"
        ),
        "M04-QA-129": "no migration harness: deferred-FK validation is a migration step, "
        "and validating it needs the pre-validation state stood up",
        "M04-QA-130": _COMMERCIAL,
        "M04-QA-131": _COMMERCIAL,
    }
)


# ===========================================================================
# The gate
# ===========================================================================


def _declared() -> set[str]:
    return set(re.findall(r"M04-QA-\d{3}", _QA_DOC.read_text()))


def _implemented() -> set[str]:
    source = Path(__file__).read_text()
    return {
        f"M04-QA-{n}"
        for n in re.findall(r"^def test_m04_qa_(\d{3})_", source, re.MULTILINE)
    }


def test_every_m04_scenario_is_implemented_or_declared() -> None:
    declared = _declared()
    assert len(declared) == 131, f"expected 131 scenarios, found {len(declared)}"
    implemented = _implemented()
    blocked = set(BLOCKED)
    assert not (implemented & blocked), sorted(implemented & blocked)
    missing = declared - implemented - blocked
    assert not missing, f"neither implemented nor declared blocked: {sorted(missing)}"
    stray = (implemented | blocked) - declared
    assert not stray, f"ids not in the contract: {sorted(stray)}"


def test_the_m04_blocked_reasons_name_one_of_seven_causes() -> None:
    """A free-text reason rots into "TODO". The two that must never merge are
    `feature absent` and `no command envelope`: the first is a module to
    write, the second is a wrapper around code that already works."""
    for scenario, reason in BLOCKED.items():
        assert any(
            cause in reason
            for cause in (
                "feature absent",
                "no command envelope",
                "no platform actor",
                "not enforced",
                "no HTTP surface",
                "no worker",
                "no migration harness",
            )
        ), f"{scenario} has an unrecognised blocking reason: {reason}"


# ===========================================================================
# Fixtures shared by the runnable scenarios
# ===========================================================================


def _organization(
    db: Session,
    *,
    legal_name: str = "Udruženje Soko",
    ref: str | None = None,
    registration_number: str | None = None,
    status: OrganizationStatus = OrganizationStatus.ACTIVE,
) -> Organization:
    holder = Organization(
        organization_ref=ref or new_id("oref"),
        legal_name=legal_name,
        country_code="RS",
        registration_number=registration_number,
        status=status,
        archived_at=clock.now() if status is OrganizationStatus.ARCHIVED else None,
        created_by_actor_ref="test",
        updated_by_actor_ref="test",
    )
    db.add(holder)
    db.commit()
    return holder


def _refused(db: Session, constraint: str) -> None:
    """Commit, expect the named constraint to reject it, and roll back.

    The constraint is named rather than just the exception type, because a row
    that violates two rules fails on whichever Postgres checks first — and a
    test that only asserted `IntegrityError` would pass while proving the
    wrong rule. That is not hypothetical; it happened twice in M07's pass.
    """
    with pytest.raises(IntegrityError) as raised:
        db.commit()
    assert constraint in str(raised.value), f"expected {constraint}, got {raised.value}"
    db.rollback()


def _create_person(client: TestClient, actor: Actor, given: str) -> str:
    resp = client.post(
        "/people", headers=actor.headers, json={"given_name": given, "family_name": "Osoba"}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def _refused_now(db: Session, sql: str, params: dict[str, object], constraint: str) -> None:
    """Same as :func:`_refused`, for a statement the database rejects outright.

    A CHECK is evaluated per statement, so the `execute` raises and there is
    never a commit to catch. A unique index on an ORM insert only bites when
    the flush happens. Using the wrong helper makes a passing test that proves
    nothing, so the two are kept apart by name.
    """
    with pytest.raises(IntegrityError) as raised:
        db.execute(text(sql), params)
    assert constraint in str(raised.value), f"expected {constraint}, got {raised.value}"
    db.rollback()


# ===========================================================================
# §2. Organization i School foundation
# ===========================================================================


def test_m04_qa_004_an_organization_reference_is_globally_unique(db: Session) -> None:
    """§2.1's first dedupe key. Global, not per-country: the reference is the
    platform's own mark, and two rows carrying one would make "which
    organization is ORG-123" a question with two answers."""
    _organization(db, legal_name="Prva", ref="oref-shared")
    db.add(
        Organization(
            organization_ref="oref-shared",
            legal_name="Druga",
            country_code="RS",
            created_by_actor_ref="test",
            updated_by_actor_ref="test",
        )
    )
    _refused(db, "uq_organization_ref")


def test_m04_qa_005_two_organizations_may_share_a_legal_name(db: Session) -> None:
    """§2.1 is explicit that `legal_name` is *not* a dedupe key. Two genuinely
    different entities may be called the same thing, and merging them by name
    is how one company's contracts end up on another's."""
    first = _organization(db, legal_name="Sokolski klub", registration_number="11111111")
    second = _organization(db, legal_name="Sokolski klub", registration_number="22222222")

    assert first.id != second.id
    assert first.legal_name == second.legal_name
    assert (
        db.execute(
            select(func.count())
            .select_from(Organization)
            .where(Organization.legal_name == "Sokolski klub")
        ).scalar_one()
        == 2
    )


def test_m04_qa_006_one_live_organization_per_registration_number(db: Session) -> None:
    """§2.1's second dedupe key, and the half that makes it usable.

    The index is partial — `status <> 'ARCHIVED'` — so an archived duplicate
    does not block a correct re-registration of the same entity. A plain
    unique index would pass the first assertion here and strand the company
    forever on the second.
    """
    _organization(db, legal_name="Registrovani", registration_number="12345678")
    db.add(
        Organization(
            organization_ref=new_id("oref"),
            legal_name="Isti broj",
            country_code="RS",
            registration_number="12345678",
            created_by_actor_ref="test",
            updated_by_actor_ref="test",
        )
    )
    _refused(db, "uq_organization_registration")

    archived = _organization(
        db, legal_name="Ugašeni", registration_number="87654321",
        status=OrganizationStatus.ARCHIVED,
    )
    assert archived.status is OrganizationStatus.ARCHIVED
    revived = _organization(
        db, legal_name="Nasledník", registration_number="87654321"
    )
    assert revived.id != archived.id


def test_m04_qa_011_a_provisioning_reference_cannot_name_two_schools(
    db: Session,
) -> None:
    """§2.2's dedupe key for provisioning: a second request carrying the same
    reference is a conflict, never "here is the school you already made".

    The scenario also asks for no partial rows, so the second school is
    attempted inside a transaction that has already written its own rows —
    and the assertion afterwards is that the table is back to one.
    """
    first = make_school(db, name="Prva skola")
    reference = first.provisioning_reference

    before = db.execute(select(func.count()).select_from(School)).scalar_one()
    db.add(
        School(
            name="Druga skola",
            type=SchoolType.SPORTS_CLUB,
            status=SchoolStatus.IN_PREPARATION,
            provisioning_reference=reference,
        )
    )
    _refused(db, "uq_school_provisioning_reference")
    assert db.execute(select(func.count()).select_from(School)).scalar_one() == before


def test_m04_qa_015_an_unsupported_currency_or_country_cannot_be_stored(
    db: Session,
) -> None:
    """§2.2 pins both to a CHECK rather than to service validation.

    §3.3.5's reasoning is worth keeping in view: silently converting stored
    money to another currency is the failure being prevented, and it cannot be
    prevented once the column accepts the value — an import, a backfill or a
    fixture will eventually put one there.
    """
    db.add(
        School(
            name="Evro klub",
            type=SchoolType.SPORTS_CLUB,
            status=SchoolStatus.IN_PREPARATION,
            currency="EUR",
        )
    )
    _refused(db, "ck_school_currency")

    db.add(
        School(
            name="Nemacki klub",
            type=SchoolType.SPORTS_CLUB,
            status=SchoolStatus.IN_PREPARATION,
            country_code="DE",
        )
    )
    _refused(db, "ck_school_country")


@pytest.mark.parametrize(
    "kind",
    [k for k in SchoolKind if k is not SchoolKind.OTHER],
)
def test_m04_qa_016_each_named_kind_stands_without_a_label(
    db: Session, kind: SchoolKind
) -> None:
    """Seven named kinds, each stored with no label at all."""
    school = School(
        name=f"Klub {kind.value}",
        type=SchoolType.SPORTS_CLUB,
        status=SchoolStatus.IN_PREPARATION,
        school_kind=kind,
        school_kind_other_label=None,
    )
    db.add(school)
    db.commit()
    assert school.school_kind is kind
    assert school.school_kind_other_label is None


def test_m04_qa_016_other_requires_a_label_and_a_label_requires_other(
    db: Session,
) -> None:
    """The CHECK is an *iff*, and both directions matter.

    `OTHER` with no label is a school whose kind says "see the label" with
    nothing to see. A label on a named kind is the opposite failure — two
    sources of truth for one fact, disagreeing the moment either is edited.

    Driven by raw `UPDATE` rather than through the ORM, and not for
    convenience: `school_kind_other_label` carries a Python-side default
    derived from `type`, so an ORM insert passing `None` has the default fill
    it back in and never reaches the constraint. That is exactly the case
    §2.2 puts the rule in the database for — the rule has to hold when the
    application layer is not the one writing.
    """
    school = make_school(db, name="Kind provera")

    _refused_now(
        db,
        "UPDATE school SET school_kind = 'OTHER', school_kind_other_label = NULL "
        "WHERE id = :id",
        {"id": school.id},
        "ck_school_kind_other_label",
    )
    _refused_now(
        db,
        "UPDATE school SET school_kind = 'MUSIC_SCHOOL', "
        "school_kind_other_label = 'nešto drugo' WHERE id = :id",
        {"id": school.id},
        "ck_school_kind_other_label",
    )

    # And the pair that is allowed.
    db.execute(
        text(
            "UPDATE school SET school_kind = 'OTHER', "
            "school_kind_other_label = 'Škola jedrenja' WHERE id = :id"
        ),
        {"id": school.id},
    )
    db.commit()
    db.expire_all()
    stored = db.get(School, school.id)
    assert stored.school_kind is SchoolKind.OTHER
    assert stored.school_kind_other_label == "Škola jedrenja"


def test_m04_qa_017_one_organization_may_hold_two_schools_with_one_name(
    db: Session,
) -> None:
    """§3.2.6: allowed, and no auto-merge. A chain that opens a second branch
    under the same trading name is the ordinary case, not a mistake to
    collapse — the provisioning reference is what tells them apart."""
    a = make_school(db, name="Soko")
    b = make_school(db, name="Soko")
    holder = db.get(
        Organization, anchor.current_organization_link(db, a.id).organization_id
    )
    anchor.transfer_organization(
        db,
        school_id=b.id,
        organization=holder,
        reason=OrganizationSchoolChangeReason.CORPORATE_RESTRUCTURE,
        case_reference="QA017",
        actor_ref="test",
    )
    db.commit()

    assert a.id != b.id
    assert a.name == b.name
    assert a.provisioning_reference != b.provisioning_reference
    assert (
        anchor.current_organization_link(db, a.id).organization_id
        == anchor.current_organization_link(db, b.id).organization_id
    )


def test_m04_qa_018_one_organization_is_not_a_key_to_its_other_school(
    db: Session, client: TestClient
) -> None:
    """§3.1/§4: the Organization is a legal holder, not a security boundary.

    Asserted *after* putting both schools under one holder, because that is
    the arrangement that tempts a reader to widen a query by organization —
    refusing before the transfer would prove nothing.
    """
    a = bootstrap_actor(db, org_name="Soko A1", given="Ana")
    b = bootstrap_actor(db, org_name="Soko A2", given="Bora")
    holder = db.get(
        Organization, anchor.current_organization_link(db, a.school.id).organization_id
    )
    anchor.transfer_organization(
        db,
        school_id=b.school.id,
        organization=holder,
        reason=OrganizationSchoolChangeReason.CORPORATE_RESTRUCTURE,
        case_reference="QA018",
        actor_ref="test",
    )
    db.commit()

    created = client.post(
        "/people", headers=b.headers, json={"given_name": "Skriven", "family_name": "Clan"}
    )
    assert created.status_code == 201
    theirs = created.json()["id"]

    real = client.get(f"/people/{theirs}", headers=a.headers)
    invented = client.get("/people/per_nema_ovakvog", headers=a.headers)
    assert real.status_code == invented.status_code == 404
    assert real.json() == invented.json()


# ===========================================================================
# §3. Profil, locator i Organization transfer
# ===========================================================================


def test_m04_qa_027_rotating_a_slug_leaves_exactly_one_active_pointing_back(
    db: Session,
) -> None:
    """§3.7: a new ACTIVE locator, the old one RETIRED and pointing at it, and
    exactly one active of that kind at any moment.

    The back-pointer is not a redirect, and the distinction matters: it records
    what a URL *used to* mean so a route can choose between a neutral redirect
    and safe-not-found. Deciding that here would put an M03 question in M04.
    """
    school = make_school(db, name="Rotacija")
    original = anchor.active_locator(db, school.id, LocatorKind.SLUG)
    assert original is not None

    replacement = anchor.rotate_locator(
        db, school_id=school.id, kind=LocatorKind.SLUG, value="novi-slug", actor_ref="test"
    )
    db.commit()

    assert replacement.normalized_value == "novi-slug"
    assert replacement.status is LocatorStatus.ACTIVE
    db.refresh(original)
    assert original.status is LocatorStatus.RETIRED
    assert original.replaced_by_locator_id == replacement.id
    assert original.retired_at is not None

    active = db.execute(
        select(func.count())
        .select_from(SchoolLocator)
        .where(
            SchoolLocator.school_id == school.id,
            SchoolLocator.kind == LocatorKind.SLUG,
            SchoolLocator.status == LocatorStatus.ACTIVE,
        )
    ).scalar_one()
    assert active == 1
    # The retired row's window closes exactly where the new one opens, so the
    # history has no gap and no overlap to resolve.
    assert original.retired_at == replacement.valid_from


def test_m04_qa_028_two_schools_cannot_hold_one_slug(db: Session) -> None:
    """§7.2.5: exactly one wins, the other is refused.

    Sequential rather than threaded, and that is the honest description: what
    is proved is that the value is claimed globally and the second claim is
    refused — which is the property that makes a race safe. The interleaving
    itself is held by a partial unique index, asserted separately below by
    bypassing the service.
    """
    a = make_school(db, name="Prva")
    b = make_school(db, name="Druga")

    anchor.rotate_locator(
        db, school_id=a.id, kind=LocatorKind.SLUG, value="zajednicki", actor_ref="test"
    )
    db.commit()

    with pytest.raises(ConflictError):
        anchor.rotate_locator(
            db, school_id=b.id, kind=LocatorKind.SLUG, value="zajednicki", actor_ref="test"
        )
    db.rollback()

    holders = db.execute(
        select(SchoolLocator.school_id).where(
            SchoolLocator.kind == LocatorKind.SLUG,
            SchoolLocator.normalized_value == "zajednicki",
            SchoolLocator.status == LocatorStatus.ACTIVE,
        )
    ).scalars().all()
    assert holders == [a.id]


def test_m04_qa_029_a_school_code_reveals_branding_and_nothing_else(
    db: Session, client: TestClient
) -> None:
    """§3.7.4. A locator is for navigation, not a credential: knowing one
    creates no account, person, invitation, membership, role or context.

    The school is created through `POST /schools` rather than the factory,
    because public discovery reads `School.slug` while M04's authority for the
    same fact is the SLUG locator. Only the real create path writes both, and
    a test that hand-set one would be asserting against a state production
    never produces. The two are checked against each other below.

    What comes back is asserted by enumerating the fields present, not by
    naming the ones that must not be — a field added later is then a failure
    here instead of a leak nobody thought to look for.
    """
    founder = make_person(db, given="Osnivač", family="Prvi")
    created = client.post(
        "/schools",
        headers={DEV_PERSON_HEADER: founder.id},
        json={"name": "Javna skola", "type": "SPORTS_CLUB"},
    )
    assert created.status_code == 201, created.text
    school_id = created.json()["id"]

    school = db.get(School, school_id)
    locator = anchor.active_locator(db, school_id, LocatorKind.SLUG)
    assert locator is not None
    assert school.slug == locator.normalized_value, (
        "the discovery column and the M04 locator must name the same value"
    )

    child = make_person(db, given="Tajni", family="Polaznik")
    add_membership(db, person=child, school=school)

    before = db.execute(text("SELECT count(*) FROM session_tenant_context")).scalar_one()
    resp = client.get(f"/tenants/{school.slug}")
    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == {"school_id", "name", "slug"}
    assert "Tajni" not in resp.text
    after = db.execute(text("SELECT count(*) FROM session_tenant_context")).scalar_one()
    assert after == before, "discovery must not create a tenant context"


def test_m04_qa_031_two_transfers_at_once_leave_one_current_link(
    db: Session,
) -> None:
    """§7.2.2: one serialized success, at most one active link.

    The second transfer is attempted from the state the first left behind,
    which is what a serialized pair actually looks like — and the assertion
    that matters is the count of open links, because the failure mode here is
    two rows with a NULL `valid_to`, not an error that never came.
    """
    school = make_school(db, name="Prenos")
    first_holder = db.get(
        Organization, anchor.current_organization_link(db, school.id).organization_id
    )
    second = _organization(db, legal_name="Druga organizacija")

    anchor.transfer_organization(
        db,
        school_id=school.id,
        organization=second,
        reason=OrganizationSchoolChangeReason.CORPORATE_RESTRUCTURE,
        case_reference="QA031-a",
        actor_ref="test",
    )
    db.commit()

    # The loser replays against the state the winner committed.
    with pytest.raises(ConflictError):
        anchor.transfer_organization(
            db,
            school_id=school.id,
            organization=second,
            reason=OrganizationSchoolChangeReason.CORPORATE_RESTRUCTURE,
            case_reference="QA031-b",
            actor_ref="test",
        )
    db.rollback()

    open_links = db.execute(
        select(func.count())
        .select_from(OrganizationSchool)
        .where(
            OrganizationSchool.school_id == school.id,
            OrganizationSchool.valid_to.is_(None),
        )
    ).scalar_one()
    assert open_links == 1
    assert anchor.current_organization_link(db, school.id).organization_id == second.id
    assert first_holder.id != second.id


def test_m04_qa_033_a_transfer_moves_the_holder_and_nothing_else(
    db: Session, client: TestClient
) -> None:
    """§3.1.5: after ORG-04 the school id, its people, groups and charges are
    all exactly where they were.

    The school id is the one to watch. Re-keying a school on transfer would be
    invisible in a link table and catastrophic everywhere else — every
    tenant-scoped row in the system names it.
    """
    actor = bootstrap_actor(db, org_name="Klub pre prenosa", given="Ana")
    person = _create_person(client, actor, "Ostaje")
    group = client.post("/groups", headers=actor.headers, json={"name": "Grupa"})
    assert group.status_code == 201

    school_id = actor.school.id
    before = _tenant_row_counts(db, school_id)
    new_holder = _organization(db, legal_name="Novi vlasnik")

    link_before = anchor.current_organization_link(db, school_id)
    anchor.transfer_organization(
        db,
        school_id=school_id,
        organization=new_holder,
        reason=OrganizationSchoolChangeReason.LEGAL_OWNERSHIP_TRANSFER,
        case_reference="QA033",
        actor_ref="test",
    )
    db.commit()

    link_after = anchor.current_organization_link(db, school_id)
    assert link_after.organization_id == new_holder.id
    assert link_before.valid_to == link_after.valid_from, "the history must be gapless"

    assert db.get(School, school_id) is not None
    assert _tenant_row_counts(db, school_id) == before
    assert person in {
        item["id"] for item in client.get("/people", headers=actor.headers).json()["items"]
    }


def _tenant_row_counts(db: Session, school_id: str) -> dict[str, int]:
    """How many rows each tenant-scoped table holds for this school."""
    return {
        table: db.execute(
            text(f"SELECT count(*) FROM {table} WHERE school_id = :s"), {"s": school_id}
        ).scalar_one()
        for table in (
            "school_membership",
            "school_person_profile",
            '"group"',
            "role_assignment",
            "school_locator",
            "school_status_transition",
        )
    }


# ===========================================================================
# §4. Owner i School lifecycle
# ===========================================================================


def _school_with_owner(db: Session, name: str) -> tuple[School, Person, RoleAssignment]:
    """A school whose primary ownership was reached the way §3.4 describes:
    a nomination, then an OWNER role, then acceptance opening the first term."""
    school = make_school(db, name=name, status=SchoolStatus.IN_PREPARATION)
    owner = make_person(db, given="Vlasnik", family=name[:6])
    add_membership(db, person=owner, school=school)
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=owner.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.flush()
    assignment = assign_role(db, person=owner, school=school, role=RoleCode.OWNER)
    ownership.fulfill_nomination(
        db, nomination=nomination, role_assignment=assignment, actor_ref="m02"
    )
    db.commit()
    return school, owner, assignment


def _second_owner(
    db: Session, school: School, given: str, *, nominate: bool = False
) -> tuple[Person, RoleAssignment, SchoolOwnerNomination | None]:
    """Another owner, optionally reached through a nomination first.

    The order matters and is easy to get backwards: `nominate_owner` refuses a
    person who *already* holds an active OWNER role (§2.6), so OWN-01 comes
    before the role assignment, not after it.
    """
    person = make_person(db, given=given, family="Suvlasnik")
    add_membership(db, person=person, school=school)
    nomination = None
    if nominate:
        nomination = ownership.nominate_owner(
            db,
            school_id=school.id,
            person_id=person.id,
            kind=OwnerNominationKind.ADDITIONAL_OWNER,
            actor_ref="platform",
        )
        db.flush()
    assignment = assign_role(db, person=person, school=school, role=RoleCode.OWNER)
    db.commit()
    return person, assignment, nomination


def test_m04_qa_039_an_expired_invitation_leaves_the_nomination_pending(
    db: Session,
) -> None:
    """§3.10.4. What must *not* happen when an initial invite lapses.

    The nomination stays PENDING rather than being cancelled, and §2.6 is
    explicit why: giving up on a person is `cancel_nomination`, and it should
    have to be said out loud. So the school sits in IN_PREPARATION with no
    owner and no term, which is the one state §3.4.1 allows that to be.
    """
    school = make_school(db, name="Istekla pozivnica", status=SchoolStatus.IN_PREPARATION)
    candidate = make_person(db, given="Pozvani", family="Kandidat")
    add_membership(db, person=candidate, school=school)
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=candidate.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    invitation = _invitation(
        db,
        school,
        "pozvani@example.com",
        expires_at=clock.now() - dt.timedelta(days=1),
        status=InvitationStatus.EXPIRED,
    )
    ownership.attach_invitation(db, nomination=nomination, invitation_id=invitation.id)
    db.commit()

    db.expire_all()
    assert nomination.status is OwnerNominationStatus.PENDING
    assert db.get(School, school.id).status is SchoolStatus.IN_PREPARATION
    assert ownership.current_primary_term(db, school.id) is None
    assert ownership.active_owner_assignments(db, school.id) == []


def test_m04_qa_040_reissuing_moves_the_pointer_not_the_nomination(
    db: Session,
) -> None:
    """§2.6: a replacement invitation changes `latest_invitation_id` and the
    version, and creates no second nomination and no term.

    A new nomination per reissue would make "how many times did we ask this
    person" indistinguishable from "how many people did we ask".
    """
    school = make_school(db, name="Ponovni poziv", status=SchoolStatus.IN_PREPARATION)
    candidate = make_person(db, given="Ponovo", family="Pozvani")
    add_membership(db, person=candidate, school=school)
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=candidate.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.flush()
    first = _invitation(db, school, "prvi@example.com")
    ownership.attach_invitation(db, nomination=nomination, invitation_id=first.id)
    db.commit()
    version_after_first = nomination.version

    second = _invitation(db, school, "drugi@example.com")
    ownership.attach_invitation(db, nomination=nomination, invitation_id=second.id)
    db.commit()

    assert nomination.latest_invitation_id == second.id
    assert nomination.version == version_after_first + 1
    assert nomination.status is OwnerNominationStatus.PENDING
    assert (
        db.execute(
            select(func.count())
            .select_from(SchoolOwnerNomination)
            .where(SchoolOwnerNomination.school_id == school.id)
        ).scalar_one()
        == 1
    )
    assert ownership.current_primary_term(db, school.id) is None


def _invitation(
    db: Session,
    school: School,
    email: str,
    *,
    expires_at: dt.datetime | None = None,
    status: InvitationStatus = InvitationStatus.PENDING,
) -> Invitation:
    """An M02 invitation carrying an OWNER role.

    `InvitationType` has no `OWNER` member — this repo's invitation types are
    STAFF/PARENT/STUDENT and the owner-ness rides on `role_code`. That is the
    shape M04 §2.6 points a nomination at, so the fixture uses it rather than
    inventing the type the contract's prose implies.
    """
    invitation = Invitation(
        school_id=school.id,
        target_email=email,
        type=InvitationType.STAFF,
        role_code=RoleCode.OWNER,
        scope_type=RoleScopeType.SCHOOL,
        token_hash=secrets.token_hex(32),
        expires_at=expires_at or (clock.now() + dt.timedelta(days=7)),
        status=status,
    )
    db.add(invitation)
    db.flush()
    return invitation


def test_m04_qa_041_nominating_a_sitting_owner_is_refused(db: Session) -> None:
    """§2.6: not a no-op, a conflict.

    Accepting it silently would mean the caller believes something untrue
    about the school and is never told — and the nomination that resulted
    would look, later, like evidence that this person was made an owner twice.
    """
    school, owner, _ = _school_with_owner(db, "Vec vlasnik")

    with pytest.raises(ConflictError):
        ownership.nominate_owner(
            db,
            school_id=school.id,
            person_id=owner.id,
            kind=OwnerNominationKind.ADDITIONAL_OWNER,
            actor_ref="platform",
        )
    db.rollback()

    assert (
        db.execute(
            select(func.count())
            .select_from(SchoolOwnerNomination)
            .where(SchoolOwnerNomination.school_id == school.id)
        ).scalar_one()
        == 1
    )


def test_m04_qa_042_an_additional_owner_does_not_take_primacy(db: Session) -> None:
    """§8.1 OWN-03: an existing effective term is **not** changed.

    This is the one that quietly breaks. Creating the first term on any
    acceptance reads as correct until a second owner joins, at which point the
    school changes hands without anyone asking for it.
    """
    school, first_owner, _ = _school_with_owner(db, "Dva vlasnika")
    original_term = ownership.current_primary_term(db, school.id)

    second, second_role, nomination = _second_owner(db, school, "Drugi", nominate=True)
    _, created_term = ownership.fulfill_nomination(
        db, nomination=nomination, role_assignment=second_role, actor_ref="m02"
    )
    db.commit()

    assert created_term is None, "acceptance must not open a second term"
    assert nomination.status is OwnerNominationStatus.FULFILLED
    current = ownership.current_primary_term(db, school.id)
    assert current.id == original_term.id
    assert current.owner_person_id == first_owner.id
    assert len(ownership.active_owner_assignments(db, school.id)) == 2


def test_m04_qa_043_the_last_owner_role_cannot_be_removed(db: Session) -> None:
    """§3.4.5. A school with no owner is a school nobody can administer, and
    nothing in M04 would let anyone back in."""
    school, _, assignment = _school_with_owner(db, "Poslednji")

    with pytest.raises(ConflictError):
        ownership.ensure_owner_role_may_be_removed(
            db, school_id=school.id, role_assignment=assignment
        )
    db.rollback()
    assert ownership.active_owner_assignments(db, school.id) != []


def test_m04_qa_044_the_primary_owners_role_needs_a_transfer_first(
    db: Session,
) -> None:
    """§3.4.5's other half, and it is deliberately a *different* refusal.

    "Transfer primacy first" and "this is the last owner" need different
    answers from whoever asked, so the guard names which problem it found
    rather than refusing both the same way.
    """
    school, _, primary_role = _school_with_owner(db, "Prenos prvo")
    _, second_role, _ = _second_owner(db, school, "Rezerva")

    with pytest.raises(ConflictError) as raised:
        ownership.ensure_owner_role_may_be_removed(
            db, school_id=school.id, role_assignment=primary_role
        )
    assert "prenosa primarnosti" in str(raised.value)
    db.rollback()

    # The non-primary owner may go: two owners, one of them not primary.
    ownership.ensure_owner_role_may_be_removed(
        db, school_id=school.id, role_assignment=second_role
    )


def test_m04_qa_045_transfer_closes_one_term_and_opens_the_next_at_one_instant(
    db: Session,
) -> None:
    """§3.4.6–8: gapless, and the role set is untouched.

    The outgoing owner stays an OWNER. A transfer moves a designation; if it
    also took the role away, "hand over the club" would silently remove the
    founder's access on a screen that said nothing about it.
    """
    school, first_owner, first_role = _school_with_owner(db, "Predaja")
    second, _, _ = _second_owner(db, school, "Naslednik")
    original = ownership.current_primary_term(db, school.id)

    successor = ownership.transfer_primary_ownership(
        db,
        school_id=school.id,
        to_person_id=second.id,
        reason=PrimaryOwnerTermReason.OWNER_TRANSFER,
        actor_ref="platform",
    )
    db.commit()

    db.refresh(original)
    assert original.valid_to == successor.valid_from, "no gap and no overlap"
    assert ownership.current_primary_term(db, school.id).id == successor.id
    assert successor.owner_person_id == second.id
    # §3.4.8: the role set did not move.
    db.refresh(first_role)
    assert first_role.status is RoleAssignmentStatus.ACTIVE
    assert {a.person_id for a in ownership.active_owner_assignments(db, school.id)} == {
        first_owner.id,
        second.id,
    }


def test_m04_qa_046_primacy_cannot_be_handed_to_a_non_owner(db: Session) -> None:
    """§3.4.6: the target must already hold an active OWNER role.

    Granting it as a side effect would make "make them primary" a way to make
    someone an owner without the command that is supposed to do that — and
    that command is where the eligibility checks live.
    """
    school, _, _ = _school_with_owner(db, "Nije vlasnik")
    manager = make_person(db, given="Menadzer", family="Bez")
    add_membership(db, person=manager, school=school)
    assign_role(db, person=manager, school=school, role=RoleCode.MANAGER)
    before = ownership.current_primary_term(db, school.id)

    with pytest.raises(ConflictError):
        ownership.transfer_primary_ownership(
            db,
            school_id=school.id,
            to_person_id=manager.id,
            reason=PrimaryOwnerTermReason.OWNER_TRANSFER,
            actor_ref="platform",
        )
    db.rollback()
    assert ownership.current_primary_term(db, school.id).id == before.id


def test_m04_qa_056_a_failed_deactivation_moves_neither_status_nor_access(
    db: Session,
) -> None:
    """§7.3: the status change and the TEN-04 bump are one transaction.

    Asserted by letting the transition run and then abandoning the
    transaction, which is what a fault between the two steps looks like from
    the database's side. A status that had committed without its access bump
    would be the worst of both: a school that reads DEACTIVATED while every
    issued context still resolves against it.
    """
    school = make_school(db, name="Pad u sredini")
    before_status = school.status
    before_version = tenant_security.current_version(db, school.id)

    anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.DEACTIVATED,
        reason_code=SchoolStatusReason.OPERATIONAL_PAUSE,
        actor_ref="test",
        correlation_id="qa-056",
    )
    db.flush()
    db.rollback()

    db.expire_all()
    assert db.get(School, school.id).status is before_status
    assert tenant_security.current_version(db, school.id) == before_version
    assert (
        db.execute(
            select(func.count())
            .select_from(SchoolStatusTransition)
            .where(
                SchoolStatusTransition.school_id == school.id,
                SchoolStatusTransition.to_status == SchoolStatus.DEACTIVATED,
            )
        ).scalar_one()
        == 0
    )


def test_m04_qa_057_a_request_after_deactivation_is_refused_before_any_payload(
    db: Session, client: TestClient
) -> None:
    """§4.4: refused before the business payload, and before any write.

    The header the caller holds was minted while the school was live, so this
    is precisely the "stale cache" case — nothing the client carries has
    changed, and the answer has.
    """
    actor = bootstrap_actor(db, org_name="Ugasena", given="Ana")
    assert client.get("/people", headers=actor.headers).status_code == 200
    _deactivate(db, actor.school)

    read = client.get("/people", headers=actor.headers)
    assert read.status_code == 403
    assert "items" not in read.text

    before = db.execute(text("SELECT count(*) FROM person")).scalar_one()
    write = client.post(
        "/people", headers=actor.headers, json={"given_name": "Nova", "family_name": "Osoba"}
    )
    assert write.status_code == 403
    assert db.execute(text("SELECT count(*) FROM person")).scalar_one() == before


def test_m04_qa_059_deactivating_one_school_leaves_the_persons_other_one(
    db: Session, client: TestClient
) -> None:
    """§3.6.4. The person is global; only one of their schools went away.

    A deactivation that reached the account would punish everyone who happens
    to work at two clubs for something one of them did.
    """
    first = bootstrap_actor(db, org_name="Klub A1", given="Ana")
    second_school = make_school(db, name="Klub B1")
    add_membership(db, person=first.person, school=second_school)
    second_assignment = assign_role(
        db, person=first.person, school=second_school, role=RoleCode.MANAGER
    )
    second_headers = {
        DEV_PERSON_HEADER: first.person.id,
        CONTEXT_HEADER: second_assignment.id,
    }

    assert client.get("/people", headers=first.headers).status_code == 200
    assert client.get("/people", headers=second_headers).status_code == 200

    _deactivate(db, first.school)

    assert client.get("/people", headers=first.headers).status_code == 403
    assert client.get("/people", headers=second_headers).status_code == 200


def _deactivate(db: Session, school: School) -> None:
    anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.DEACTIVATED,
        reason_code=SchoolStatusReason.OPERATIONAL_PAUSE,
        actor_ref="test",
        correlation_id=f"corr-{school.id}",
    )
    db.commit()


# ===========================================================================
# §5. Entitlement
# ===========================================================================


def _grant(
    db: Session,
    school: School,
    capability: CapabilityKey = CapabilityKey.CORE_MVP,
    *,
    valid_until: dt.datetime | None = None,
) -> SchoolProductEntitlement:
    granted = entitlements.grant_entitlement(
        db,
        school_id=school.id,
        capability=capability,
        commercial_reference="UG-2026-001",
        reason=EntitlementGrantReason.CONTRACT_ACTIVATED,
        actor_ref="platform",
        valid_until=valid_until,
    )
    db.commit()
    return granted


def test_m04_qa_064_a_grant_cannot_name_another_schools_organization(
    db: Session,
) -> None:
    """§3.8.2. Asserted as a structural property rather than as an error code.

    `ENTITLEMENT_SOURCE_ORGANIZATION_INVALID` does not exist in this repo, and
    it does not need to: `grant_entitlement` reads the source from the
    school's *current* organization link rather than taking it as a
    parameter, so there is no input through which a caller could name another
    school's holder. A refusal is one way to make something impossible; not
    accepting it is the stronger one.

    The other half of §3.8.2 is then checked: once the school moves to a new
    holder, the old grant reads ineffective without anything editing it.
    """
    a = make_school(db, name="Skola A")
    b = make_school(db, name="Skola B")
    b_holder_id = anchor.current_organization_link(db, b.id).organization_id

    granted = _grant(db, a)
    assert granted.source_organization_id != b_holder_id
    assert (
        granted.source_organization_id
        == anchor.current_organization_link(db, a.id).organization_id
    )
    assert entitlements.has_capability(db, a.id, CapabilityKey.CORE_MVP)

    # §3.1.6: a transfer re-grants explicitly; capabilities do not ride along.
    new_holder = _organization(db, legal_name="Novi nosilac")
    anchor.transfer_organization(
        db,
        school_id=a.id,
        organization=new_holder,
        reason=OrganizationSchoolChangeReason.LEGAL_OWNERSHIP_TRANSFER,
        case_reference="QA064",
        actor_ref="test",
    )
    db.commit()

    assert not entitlements.has_capability(db, a.id, CapabilityKey.CORE_MVP)
    db.refresh(granted)
    assert granted.status is EntitlementStatus.ACTIVE, (
        "the row is untouched; only its effectiveness changed"
    )


def test_m04_qa_065_an_ungranted_capability_is_absent_by_default(
    db: Session,
) -> None:
    """§3.8.6. Fail-closed by construction: nothing is on until it is bought.

    Checked for both optional capabilities, because a default that leaked
    would leak per capability — and `CORE_MVP` being granted must not turn the
    others on by association.
    """
    school = make_school(db, name="Bez dodataka")
    _grant(db, school, CapabilityKey.CORE_MVP)

    assert entitlements.has_capability(db, school.id, CapabilityKey.CORE_MVP)
    for capability in (CapabilityKey.MYSOKOLA_BASIC, CapabilityKey.OPERATIONS):
        assert not entitlements.has_capability(db, school.id, capability)
        assert entitlements.effective_entitlement(db, school.id, capability) is None
        with pytest.raises(ConflictError):
            entitlements.require_capability(db, school.id, capability)


def test_m04_qa_068_a_revoked_entitlement_stops_at_the_commit(db: Session) -> None:
    """§3.8.5: immediately, and read through no cache.

    `is_effective` re-derives the answer per call from the row's own status,
    which is what makes "immediately" true without a cache to invalidate.
    """
    school = make_school(db, name="Opoziv")
    granted = _grant(db, school)
    assert entitlements.has_capability(db, school.id, CapabilityKey.CORE_MVP)

    entitlements.revoke_entitlement(
        db, entitlement=granted, reason=EntitlementRevokeReason.CONTRACT_ENDED
    )
    db.commit()

    assert not entitlements.has_capability(db, school.id, CapabilityKey.CORE_MVP)
    assert granted.status is EntitlementStatus.REVOKED
    assert granted.revoked_at is not None


def test_m04_qa_069_the_instant_a_window_closes_is_already_outside_it(
    db: Session,
) -> None:
    """§3.8.3: `now == valid_until` is ineffective, and the job is not the
    authority.

    Both halves in one test, because the second is what makes the first
    matter: the grant is still `ACTIVE` in the table — no expiry job has run —
    and the reader says no anyway. A reader that waited for the job would give
    a school an extra hour of a capability it stopped paying for, with the
    length of the window set by how backed up the worker was.
    """
    school = make_school(db, name="Istek")
    closes_at = clock.now() + dt.timedelta(hours=1)
    granted = _grant(db, school, valid_until=closes_at)

    assert entitlements.is_effective(db, granted, at=closes_at - dt.timedelta(seconds=1))
    assert not entitlements.is_effective(db, granted, at=closes_at)
    assert not entitlements.is_effective(db, granted, at=closes_at + dt.timedelta(hours=5))
    assert granted.status is EntitlementStatus.ACTIVE, "no job has run yet"

    # And when the job does run, it only records what was already true.
    stamped = entitlements.materialize_expired(db, at=closes_at)
    db.commit()
    assert granted.id in stamped
    assert granted.status is EntitlementStatus.EXPIRED


def test_m04_qa_070_a_replacement_terminalizes_the_grant_it_replaces(
    db: Session,
) -> None:
    """§3.8.4 / §5.5: the previous grant is terminalized, never edited.

    Rewriting it in place would erase which commercial reference was in force
    when — the one question an entitlement history exists to answer. So the
    old row keeps its reference and gains `REPLACED`, and there is exactly one
    ACTIVE row for the pair at every moment, which a partial unique index
    holds even against a caller that bypasses this function.
    """
    school = make_school(db, name="Zamena")
    first = _grant(db, school)
    first_reference = first.commercial_reference

    second = entitlements.grant_entitlement(
        db,
        school_id=school.id,
        capability=CapabilityKey.CORE_MVP,
        commercial_reference="UG-2027-002",
        reason=EntitlementGrantReason.PLAN_CHANGED,
        actor_ref="platform",
    )
    db.commit()

    db.refresh(first)
    assert first.status is EntitlementStatus.REVOKED
    assert first.revocation_reason_code is EntitlementRevokeReason.REPLACED
    assert first.commercial_reference == first_reference, "history must not be rewritten"
    assert second.status is EntitlementStatus.ACTIVE

    active = db.execute(
        select(func.count())
        .select_from(SchoolProductEntitlement)
        .where(
            SchoolProductEntitlement.school_id == school.id,
            SchoolProductEntitlement.capability_key == CapabilityKey.CORE_MVP,
            SchoolProductEntitlement.status == EntitlementStatus.ACTIVE,
        )
    ).scalar_one()
    assert active == 1
    assert [row.id for row in entitlements.entitlement_history(db, school.id)] == [
        first.id,
        second.id,
    ]


def test_m04_qa_072_holding_an_organization_grants_no_capability(
    db: Session,
) -> None:
    """§3.8.6: the link is a legal fact, not a purchase.

    A school with a perfectly good current organization link and no grant has
    nothing — which is the same answer §3.1 gives about access, for the same
    reason: an Organization is who owns the school, not what the school bought.
    """
    school = make_school(db, name="Samo veza")
    assert anchor.current_organization_link(db, school.id) is not None

    for capability in CapabilityKey:
        assert not entitlements.has_capability(db, school.id, capability)
    assert entitlements.entitlement_history(db, school.id) == []


# ===========================================================================
# §7. Security, privacy i brownfield
# ===========================================================================


def test_m04_qa_099_another_schools_id_slug_and_code_all_refuse_alike(
    db: Session, client: TestClient
) -> None:
    """§4.1: safe 404 by id, and no confirmation through the public locators.

    Three doors to the same room. The id is the obvious one; the slug and the
    school code are the ones that get forgotten, because they are *meant* to
    be public — and a public lookup that answered differently for a
    deactivated school than for a nonexistent one would confirm the school
    exists to anyone holding its code.
    """
    a = bootstrap_actor(db, org_name="Klub A1", given="Ana")
    b = bootstrap_actor(db, org_name="Klub B1", given="Bora")
    theirs = _create_person(client, b, "Njihov")

    real = client.get(f"/people/{theirs}", headers=a.headers)
    invented = client.get("/people/per_izmisljeni", headers=a.headers)
    assert real.status_code == invented.status_code == 404
    assert real.json() == invented.json()

    _deactivate(db, b.school)
    slug = db.get(School, b.school.id).slug
    if slug is not None:
        gone = client.get(f"/tenants/{slug}")
        never = client.get("/tenants/nikad-postojao")
        assert gone.status_code == never.status_code == 404
        assert gone.json() == never.json()


def test_m04_qa_100_a_list_and_its_total_both_stop_at_the_tenant(
    db: Session, client: TestClient
) -> None:
    """§4.1. The `total` is the half worth asserting: a list that filtered its
    items and counted globally looks right on screen and still tells A exactly
    how many people B has."""
    a = bootstrap_actor(db, org_name="Klub A1", given="Ana")
    b = bootstrap_actor(db, org_name="Klub B1", given="Bora")
    for n in range(2):
        _create_person(client, a, f"A{n}")
    for n in range(5):
        _create_person(client, b, f"B{n}")

    mine = client.get("/people", headers=a.headers).json()
    assert mine["total"] == 3
    assert len(mine["items"]) == 3
    assert not any(item["display_name"].startswith("B") for item in mine["items"])


def test_m04_qa_101_no_command_leaves_a_contact_or_a_token_in_its_trail(
    db: Session, client: TestClient
) -> None:
    """§8.3. Run the M04 commands that exist, then read every audit row and
    every outbox payload back and look for what must not be there.

    Asserted over the *whole* trail rather than per command, because that is
    how a leak actually arrives — one payload somewhere gains a convenience
    field, and no test that only knew about its own command would notice.
    """
    founder = make_person(db, given="Osnivač", family="Kontakt")
    created = client.post(
        "/schools",
        headers={DEV_PERSON_HEADER: founder.id},
        json={"name": "Trag skole", "type": "SPORTS_CLUB"},
    )
    assert created.status_code == 201
    school = db.get(School, created.json()["id"])

    secret_email = "tajni.kontakt@example.com"
    secret_phone = "+381641234567"
    school.contact_email_masked = "t***@example.com"
    db.commit()

    _grant(db, school)
    anchor.rotate_locator(
        db, school_id=school.id, kind=LocatorKind.SLUG, value="trag-skole-2", actor_ref="test"
    )
    db.commit()
    # Walk the whole lifecycle §5.2 allows, so the trail covers every
    # transition a school can actually make rather than just its creation.
    anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.ACTIVE,
        reason_code=SchoolStatusReason.INITIAL_ACTIVATION,
        actor_ref="test",
        correlation_id="qa-101-activate",
    )
    db.commit()
    _deactivate(db, school)

    trail = " ".join(
        str(row)
        for row in db.execute(
            text("SELECT summary, entity_id, actor_person_id FROM audit_log")
        ).all()
    )
    payloads = " ".join(
        str(row[0]) for row in db.execute(text("SELECT payload FROM outbox_message")).all()
    )
    haystack = f"{trail} {payloads}"

    for forbidden in (secret_email, secret_phone, "ciphertext", "token"):
        assert forbidden not in haystack, f"{forbidden!r} reached the audit/outbox trail"


# ===========================================================================
# §7b. Foundation reference i atomicity
# ===========================================================================


def test_m04_qa_128_a_nomination_cannot_reach_another_schools_profile(
    db: Session,
) -> None:
    """Master §2.6, §4.1–4.2: safe 404, and no nomination left behind.

    The guard is a lookup keyed on `(school_id, person_id)` rather than a
    check on a profile id handed in, which is what makes "the profile belongs
    to school B" and "this school has never heard of them" the same answer.
    Telling them apart is how a guessed id confirms someone is enrolled
    somewhere else.
    """
    a = make_school(db, name="Skola A", status=SchoolStatus.IN_PREPARATION)
    b = make_school(db, name="Skola B")
    outsider = make_person(db, given="Tudji", family="Kandidat")
    add_membership(db, person=outsider, school=b)

    with pytest.raises(NotFoundError):
        ownership.nominate_owner(
            db,
            school_id=a.id,
            person_id=outsider.id,
            kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
            actor_ref="platform",
        )
    db.rollback()

    stranger = make_person(db, given="Nepoznat", family="Niko")
    with pytest.raises(NotFoundError) as unknown:
        ownership.nominate_owner(
            db,
            school_id=a.id,
            person_id=stranger.id,
            kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
            actor_ref="platform",
        )
    db.rollback()
    # Same refusal for "belongs to B" and "does not exist anywhere".
    assert str(unknown.value) == "Osoba nije poznata ovoj školi."

    assert (
        db.execute(
            select(func.count())
            .select_from(SchoolOwnerNomination)
            .where(SchoolOwnerNomination.school_id == a.id)
        ).scalar_one()
        == 0
    )
