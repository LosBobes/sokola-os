"""M03 §2: the 52 numbered QA scenarios, under the gate #115 established.

Same shape as `test_m07_qa_traceability.py` and `test_m06_qa_traceability.py`:
each runnable scenario is a test named for its id, the rest are declared in
`BLOCKED` with a reason drawn from a closed vocabulary, and a gate fails if any
of the 52 is neither. Nothing is skipped.

M03 is the first module where the blocked half is dominated by *layers this
suite is not*. Sixteen of §2's scenarios describe behaviour that lives in the
browser (a stale response discarded by context version, a PWA that has gone
offline, a back button, an unsaved form) or in a worker that does not exist
(platform cron fan-out, a queued export re-checking access). Those are not
"no HTTP surface" and they are not unwritten domain code; they are a different
tier. The reason vocabulary below keeps them apart, because filing all three
under one word is how a test suite starts reporting a 60% that means nothing.

One scenario deserves reading before the rest. §2's M03-QA-013 asks for
`404 TENANT_RESOURCE_NOT_FOUND_SAFE` "istog oblika kao nepostojeći ID". Those
two halves pull against each other: a code that names cross-tenant refusal
*specifically* is exactly what lets a prober tell "belongs to another school"
from "does not exist", which is the confirmation §8 exists to deny. This repo
answers both with one code, so the property holds and the name does not. The
tests below assert the property — byte-identical envelopes — and the
divergence is recorded as F-36 rather than decided here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from app.application.available_contexts import (
    MAX_PAGE_SIZE,
    list_available_contexts,
)
from app.application.effective_permissions import (
    effective_permissions,
    permissions_for_role_keys,
)
from app.application.tenant_context import get_active_tenant_context
from app.common.errors import (
    BadRequestError,
    TenantContextNotAvailableError,
    TenantContextStaleError,
    TenantSwitchConflictError,
)
from app.domains.groups.models import Group
from app.domains.identity import sessions
from app.domains.identity.accounts import create_account_with_identity
from app.domains.identity.auth_enums import GOOGLE_ISSUER, GOOGLE_PROVIDER
from app.domains.identity.auth_models import AuthIdentity, AuthSession, UserAccount
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode
from app.domains.identity.models import Person, RoleAssignment
from app.domains.organization.enums import OrganizationSchoolChangeReason
from app.domains.organization.models import Organization
from app.domains.people.enums import GuardianAccessStatus
from app.domains.people.models import ExternalPersonReference, GuardianSchoolAccess
from app.domains.school import anchor
from app.domains.school.enums import (
    MembershipStatus,
    SchoolStatus,
    SchoolStatusReason,
)
from app.domains.school.models import School, SchoolMembership
from app.domains.tenancy import context as tenant_context
from app.domains.tenancy import security as tenant_security
from app.domains.tenancy.enums import (
    START_ROUTE_REGULAR,
    WORKSPACE_ADMIN,
    WORKSPACE_GUARDIAN,
    WORKSPACE_INSTRUCTOR,
    ContextInvalidationReason,
    SchoolMode,
    TenantContextStatus,
    TenantInvalidationReason,
)
from app.domains.tenancy.models import SessionTenantContext
from app.platform.outbox.models import OutboxMessage
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import (
    Actor,
    add_actor,
    add_membership,
    assign_role,
    bootstrap_actor,
    make_child_with_guardian,
    make_person,
    make_school,
)

_QA_DOC = (
    Path(__file__).resolve().parents[3]
    / "docs/spec/v5.7/04-MODULSKI-UGOVORI/03-M03-MULTI-TENANCY"
    / "02-M03-QA-I-TRACEABILITY.md"
)

SECRET = "test-secret"


#: Six causes, and the reason test below refuses a seventh.
#:
#: They are kept apart because they have six different fixes. "Web client"
#: needs a React test and a store that knows its context version; "no worker"
#: needs a runner that does not exist; "feature absent" needs the domain code
#: written; "no HTTP surface" needs a router over a service that is already
#: here; the two harness causes need a test rig, not a line of product code.
#: Collapsing them would make a schedulable list look like one impossible one.
BLOCKED: dict[str, str] = {
    "M03-QA-006": (
        "feature absent: §6.2's `SETUP_ONLY` mode is computed and returned, but "
        "nothing enforces it — there is no `TENANT_SETUP_ONLY` refusal and no "
        "guard that reads the mode before admitting a regular Core command (F-28)"
    ),
    "M03-QA-008": (
        "feature absent: TEN-01 moves the context version correctly but writes "
        "no audit entry and enqueues no outbox event, so the switch leaves no "
        "record for the half of the scenario that asks for one (F-38)"
    ),
    "M03-QA-010": (
        "no HTTP surface: TEN-01 exists only as `tenant_context.select_context`, "
        "so there is no request id to retry and no idempotency store in front "
        "of it (F-38)"
    ),
    "M03-QA-011": (
        "no HTTP surface: same missing TEN-01 endpoint — and with it the "
        "`TENANT_IDEMPOTENCY_KEY_REUSED` code, which no module defines (F-38)"
    ),
    "M03-QA-018": (
        "feature absent: there is no export. M12/privacy fulfilment is a manual "
        "staff attestation with no generated artifact, storage object or job"
    ),
    "M03-QA-024": (
        "feature absent: neither a platform role nor `SupportAccessGrant` exists "
        "anywhere in app/, so there is no platform administrator to refuse"
    ),
    "M03-QA-026": (
        "feature absent: the API holds no response or result cache, so there is "
        "no cache key policy to carry a tenant dimension"
    ),
    "M03-QA-027": (
        "feature absent: there is no `TenantExecutionContext` wrapper around "
        "tenant-scoped queries and no `TENANT_ISOLATION_FAILURE` code; scoping "
        "is per-query today, so a query written without it simply has no tenant"
    ),
    "M03-QA-029": "web client: response discard by context version is store logic in apps/web",
    "M03-QA-030": (
        "feature absent: no commit-time tenant recheck for high-risk mutations; "
        "the tenant guard runs once, in the request dependency"
    ),
    "M03-QA-034": (
        "feature absent: the version/status half is covered by M03-QA-035, but "
        "there is no websocket to close and no queued job to stop"
    ),
    "M03-QA-036": "web client: PWA offline state and the service worker live in apps/web",
    "M03-QA-037": "web client: history navigation and route re-validation live in apps/web",
    "M03-QA-038": "web client: unsaved-form warning and draft discard live in apps/web",
    "M03-QA-039": "web client: there is no realtime channel, and the store guard is in apps/web",
    "M03-QA-040": "web client: deep-link confirmation and prefetch policy live in apps/web",
    "M03-QA-041": "no worker: there is no platform cron or per-tenant fan-out runner",
    "M03-QA-042": "no worker: there is no export job, queued or otherwise",
    "M03-QA-044": "no worker: no job payload carries a school scope because no job runner exists",
    "M03-QA-045": (
        "no migration harness: `d2a95e13c7f4` does backfill deterministically "
        "from an unambiguous membership path, but proving it needs alembic "
        "stopped at the prior revision, legacy rows seeded, and the step "
        "re-run — and the suite starts from a database already at head"
    ),
    "M03-QA-046": (
        "no migration harness: `a4d76f2b91c0` does abort on an unmappable "
        "status rather than guessing, for the same untestable reason as "
        "M03-QA-045"
    ),
    "M03-QA-047": (
        "no migration harness: CI runs `alembic upgrade head` on an empty "
        "database, which is the fresh-install half; there is no released prior "
        "schema to upgrade from and no rig to stand one up"
    ),
    "M03-QA-051": (
        "feature absent: TEN-04 `tenant_security.invalidate` takes no request id "
        "and is not idempotent — calling it twice bumps the access version "
        "twice, which is the opposite of what this scenario requires (F-38)"
    ),
    "M03-QA-052": "no ops harness: the repo has no backup or restore tooling to exercise",
}


# ===========================================================================
# The gate
# ===========================================================================


def _declared() -> set[str]:
    return set(re.findall(r"M03-QA-\d{3}", _QA_DOC.read_text()))


def _implemented() -> set[str]:
    source = Path(__file__).read_text()
    return {
        f"M03-QA-{n}"
        for n in re.findall(r"^def test_m03_qa_(\d{3})_", source, re.MULTILINE)
    }


def test_every_m03_scenario_is_implemented_or_declared() -> None:
    declared = _declared()
    assert len(declared) == 52, f"expected 52 scenarios, found {len(declared)}"
    implemented = _implemented()
    blocked = set(BLOCKED)
    assert not (implemented & blocked), sorted(implemented & blocked)
    missing = declared - implemented - blocked
    assert not missing, f"neither implemented nor declared blocked: {sorted(missing)}"
    stray = (implemented | blocked) - declared
    assert not stray, f"ids not in the contract: {sorted(stray)}"


def test_the_m03_blocked_reasons_name_one_of_six_causes() -> None:
    """A free-text reason rots into "TODO". Constraining it means a seventh
    cause has to be added deliberately — and in particular keeps "web client"
    and "no worker", which are whole missing tiers, from being absorbed into
    "feature absent", which is a morning's work."""
    for scenario, reason in BLOCKED.items():
        assert any(
            cause in reason
            for cause in (
                "feature absent",
                "no HTTP surface",
                "web client",
                "no worker",
                "no migration harness",
                "no ops harness",
            )
        ), f"{scenario} has an unrecognised blocking reason: {reason}"


# ===========================================================================
# Shared seed (§1's minimal fixture, built per test rather than per module so
# nothing leaks between scenarios)
# ===========================================================================


def _signed_in(
    db: Session, subject: str
) -> tuple[Person, UserAccount, AuthSession, str]:
    """A real account with a real session, and the credential that opens it.

    The credential comes back because §9's promise is about the *session*
    surviving a cleared context, and the only honest way to ask whether a
    session is still usable is to use it.
    """
    person = make_person(db, given="K", family=subject[-6:])
    account, identity = create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
    )
    session, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    return person, account, session, credential


def _member_of(
    db: Session,
    person: Person,
    school: School,
    *roles: RoleCode,
) -> None:
    """Membership evidence **and** a role assignment, which §6.1 needs both of."""
    add_membership(db, person=person, school=school)
    for role in roles or (RoleCode.MANAGER,):
        assign_role(db, person=person, school=school, role=role)


def _select(
    db: Session,
    session: AuthSession,
    account: UserAccount,
    school: School,
    workspace: str = WORKSPACE_ADMIN,
    expected: int | None = None,
) -> SessionTenantContext:
    context = tenant_context.select_context(
        db,
        session=session,
        account=account,
        school=school,
        workspace_key=workspace,
        expected_context_version=expected,
    )
    db.commit()
    return context


def _chooser(db: Session, person: Person, account: UserAccount, **kwargs):
    return list_available_contexts(
        db, person_id=person.id, user_account_id=account.id, **kwargs
    )


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
# A. Izbor i lifecycle konteksta (§§5.3–5.5, 6, 9–10, 12–14)
# ===========================================================================


def test_m03_qa_001_one_school_one_workspace_needs_no_chooser(db: Session) -> None:
    """X03 may be skipped, one context row is created, and the start route
    matches the workspace.

    "May be skipped" is a property of the answer, not of the UI: the chooser
    returns exactly one school with exactly one option, so there is nothing to
    choose. Asserting that is what makes the skip safe — a client that skips a
    two-option answer would be picking on the person's behalf.
    """
    person, account, session, credential = _signed_in(db, "sub-qa-001")
    school = make_school(db, name="Jedina")
    _member_of(db, person, school, RoleCode.MANAGER)

    page = _chooser(db, person, account)
    assert len(page.items) == 1
    assert page.next_cursor is None
    assert len(page.items[0].workspace_options) == 1

    only_option = page.items[0].workspace_options[0].workspace_key
    context = _select(db, session, account, school, only_option)
    rows = db.execute(
        select(func.count())
        .select_from(SessionTenantContext)
        .where(SessionTenantContext.session_id == session.id)
    ).scalar_one()
    assert rows == 1

    active = get_active_tenant_context(
        db, context=context, account=account, person_id=person.id, secret=SECRET
    )
    assert active.school_mode is SchoolMode.REGULAR
    assert active.allowed_start_route == START_ROUTE_REGULAR
    assert active.workspace_key == context.workspace_key


def test_m03_qa_002_two_schools_are_offered_without_operational_data(
    db: Session,
) -> None:
    """TEN-Q01 returns only the allowed schools with their workspace options,
    and §5.4's forbidden list is checked by enumerating the fields that exist
    rather than by naming the ones that must not — a field added later is then
    a failure here instead of a leak nobody looked for."""
    person, account, _, _ = _signed_in(db, "sub-qa-002")
    a = make_school(db, name="Alfa")
    b = make_school(db, name="Beta")
    other = make_school(db, name="Tudja")
    _member_of(db, person, a, RoleCode.MANAGER)
    _member_of(db, person, b, RoleCode.TRAINER)

    page = _chooser(db, person, account)
    assert {item.school_id for item in page.items} == {a.id, b.id}
    assert other.id not in {item.school_id for item in page.items}
    assert {
        item.workspace_options[0].workspace_key for item in page.items
    } == {WORKSPACE_ADMIN, WORKSPACE_INSTRUCTOR}

    allowed = {
        "school_id",
        "school_display_name",
        "school_mode",
        "workspace_options",
        "last_used_workspace_key",
    }
    assert set(type(page.items[0]).__dataclass_fields__) == allowed


def test_m03_qa_003_two_roles_in_one_school_are_one_context_two_workspaces(
    db: Session,
) -> None:
    """§6.4: one School entry, two `workspace_key` options — and M05 still
    computes the union of both roles.

    The union is the half that is easy to lose. If choosing the GUARDIAN
    workspace narrowed what the person may do, `workspace_key` would have
    become an authorization input, which §3 forbids in as many words.

    Proving "union" needs a pair whose union differs from both an intersection
    and a rank lookup, and GUARDIAN/INSTRUCTOR is not that pair: revision 1.3
    binds neither of them to anything, so every operation over the two gives
    the empty set and an intersection would pass. So the union is proved on
    OWNER + TRAINER, where an intersection would give nothing and the answer
    is OWNER's whole set, and the GUARDIAN/INSTRUCTOR person is checked
    against the union of exactly their own two role keys.
    """
    person, account, _, _ = _signed_in(db, "sub-qa-003")
    school = make_school(db, name="Dvostruka")
    _member_of(db, person, school, RoleCode.PARENT, RoleCode.TRAINER)

    page = _chooser(db, person, account)
    assert len(page.items) == 1
    keys = {option.workspace_key for option in page.items[0].workspace_options}
    assert keys == {WORKSPACE_GUARDIAN, WORKSPACE_INSTRUCTOR}

    assert effective_permissions(
        db, person_id=person.id, school_id=school.id
    ) == permissions_for_role_keys(db, role_keys=frozenset({"GUARDIAN", "INSTRUCTOR"}))

    owning_trainer = make_person(db, given="Vlasnik", family="Trener")
    _member_of(db, owning_trainer, school, RoleCode.OWNER, RoleCode.TRAINER)
    owner_only = permissions_for_role_keys(db, role_keys=frozenset({"OWNER"}))
    trainer_only = permissions_for_role_keys(db, role_keys=frozenset({"INSTRUCTOR"}))
    assert owner_only, "revision 1.3 must bind OWNER, or this proves nothing"
    assert (
        effective_permissions(db, person_id=owning_trainer.id, school_id=school.id)
        == owner_only | trainer_only
    )


def test_m03_qa_004_no_allowed_combination_is_a_neutral_empty_answer(
    db: Session, client: TestClient
) -> None:
    """§12: a successful empty result, and X04's neutral `TENANT_CONTEXT_REQUIRED`
    — neither of which says which schools the person used to be able to open."""
    person, account, _, _ = _signed_in(db, "sub-qa-004")
    gone = make_school(db, name="Nekadasnja")
    add_membership(db, person=person, school=gone, status=MembershipStatus.TERMINATED)
    assign_role(db, person=person, school=gone, role=RoleCode.MANAGER)

    page = _chooser(db, person, account)
    assert page.items == ()
    assert page.next_cursor is None

    registered = client.post(
        "/auth/password/register",
        json={
            "email": "qa004@example.com",
            "password": "longenough1",
            "given_name": "Bez",
            "family_name": "Skole",
        },
    )
    assert registered.status_code == 200
    resp = client.get("/tenant/context")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "TENANT_CONTEXT_REQUIRED"
    assert "Nekadasnja" not in resp.text


def test_m03_qa_005_a_revoked_remembered_tenant_is_dropped_not_offered(
    db: Session,
) -> None:
    """The last-used hint is a display convenience, so it must not outlive the
    access it points at. Here the usage row for A survives a revocation and the
    chooser still refuses to offer A — the hint is read after the allow-list is
    built, never used to build it."""
    person, account, session, credential = _signed_in(db, "sub-qa-005")
    a = make_school(db, name="Ranija")
    b = make_school(db, name="Preostala")
    _member_of(db, person, a, RoleCode.MANAGER)
    _member_of(db, person, b, RoleCode.MANAGER)
    _select(db, session, account, a)

    membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.school_id == a.id,
            SchoolMembership.person_id == person.id,
        )
    ).scalar_one()
    membership.status = MembershipStatus.TERMINATED
    membership.termination_reason_code = "QA005"
    membership.end_date = membership.start_date
    db.commit()

    page = _chooser(db, person, account)
    assert [item.school_id for item in page.items] == [b.id]

    context = tenant_context.current(db, session.id)
    with pytest.raises(TenantContextNotAvailableError):
        tenant_context.resolve(
            db, context=context, account=account, person_id=person.id
        )


def test_m03_qa_007_a_deactivated_school_offers_nothing_and_loses_nothing(
    db: Session,
) -> None:
    """§6.3: no context opens. §9.4's other half is as load-bearing — the
    school's rows are still there. Deactivation is a door closing, not a
    deletion, and a test that only checked the refusal would pass against an
    implementation that dropped the data."""
    person, account, session, credential = _signed_in(db, "sub-qa-007")
    school = make_school(db, name="Zatvorena")
    _member_of(db, person, school, RoleCode.MANAGER)
    context = _select(db, session, account, school)
    _deactivate(db, school)

    assert _chooser(db, person, account).items == ()
    with pytest.raises(TenantContextNotAvailableError):
        tenant_context.resolve(
            db, context=context, account=account, person_id=person.id
        )

    db.expire_all()
    assert db.get(School, school.id) is not None
    assert (
        db.execute(
            select(func.count())
            .select_from(SchoolMembership)
            .where(SchoolMembership.school_id == school.id)
        ).scalar_one()
        == 1
    )


def test_m03_qa_009_clearing_drops_the_tenant_not_the_session(db: Session) -> None:
    """TEN-02. Two things at once: the M01 session survives, and the *other*
    session of the same account is untouched — §9 keeps a context per session
    precisely so that leaving a school in one tab is not an account-wide act."""
    person, account, first, credential = _signed_in(db, "sub-qa-009")
    identity = db.execute(
        select(AuthIdentity).where(AuthIdentity.user_account_id == account.id)
    ).scalar_one()
    second, second_credential = sessions.issue_session(
        db, account=account, identity=identity
    )
    db.commit()

    school = make_school(db, name="Ista")
    _member_of(db, person, school, RoleCode.MANAGER)
    _select(db, first, account, school)
    _select(db, second, account, school)

    tenant_context.clear_context(db, session_id=first.id)
    db.commit()

    cleared = tenant_context.current(db, first.id)
    assert cleared.status is TenantContextStatus.INVALIDATED
    assert cleared.invalidation_reason_code is ContextInvalidationReason.USER_CLEARED
    # The M01 session that held the cleared context is still a session: TEN-02
    # is "I am done with this school", not a logout.
    assert sessions.validate_session(db, credential) is not None
    assert sessions.validate_session(db, second_credential) is not None
    # And the other tab's choice did not move.
    untouched = tenant_context.current(db, second.id)
    assert untouched.status is TenantContextStatus.ACTIVE
    assert untouched.school_id == school.id


def test_m03_qa_012_the_chooser_is_bounded_and_pages_without_gaps(
    db: Session,
) -> None:
    """§12/§20: at most 100 schools per page, a stable cursor, stably sorted
    workspaces, and every school exactly once across the walk.

    Built at 104 schools rather than 101 so the last page is short — an
    off-by-one in the cursor comparison shows up as a duplicate or a gap only
    when the final page is not full.
    """
    person, account, _, _ = _signed_in(db, "sub-qa-012")
    schools = []
    for n in range(104):
        school = make_school(db, name=f"Skola {n:03d}")
        _member_of(db, person, school, RoleCode.PARENT, RoleCode.TRAINER)
        schools.append(school)

    with pytest.raises(BadRequestError):
        _chooser(db, person, account, page_size=MAX_PAGE_SIZE + 1)

    seen: list[str] = []
    cursor = None
    while True:
        page = _chooser(db, person, account, cursor=cursor, page_size=MAX_PAGE_SIZE)
        assert len(page.items) <= MAX_PAGE_SIZE
        for item in page.items:
            orders = [option.display_order for option in item.workspace_options]
            assert orders == sorted(orders)
        seen.extend(item.school_id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert len(seen) == len(set(seen)) == 104
    assert set(seen) == {school.id for school in schools}


# ===========================================================================
# B. Cross-tenant i object-level zaštita (§§7–8, 13)
# ===========================================================================


def _two_tenants(db: Session) -> tuple[Actor, Actor]:
    """One actor in each of two unrelated schools, both with staff rights."""
    a = bootstrap_actor(db, org_name="Alfa klub", given="Ana")
    b = bootstrap_actor(db, org_name="Beta klub", given="Bora")
    return a, b


def _create_person(client: TestClient, actor: Actor, given: str) -> str:
    resp = client.post(
        "/people",
        headers=actor.headers,
        json={"given_name": given, "family_name": "Osoba"},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def test_m03_qa_013_another_tenants_id_is_indistinguishable_from_no_id(
    db: Session, client: TestClient
) -> None:
    """§8's whole point, and the assertion is equality rather than a status code.

    Two 404s with different bodies are still an oracle: a prober who can see
    *any* difference — code, message, field order — can sort guessed ids into
    "exists elsewhere" and "does not exist", which is the confirmation §8
    exists to deny. So the refusal for B's real person and the refusal for a
    made-up id are compared byte for byte.

    §2 names `TENANT_RESOURCE_NOT_FOUND_SAFE` for this. This repo answers both
    cases with `NOT_FOUND`, which satisfies the indistinguishability the same
    sentence demands; a code reserved for the cross-tenant case would defeat
    it. Recorded as F-36 rather than decided here.
    """
    a, b = _two_tenants(db)
    theirs = _create_person(client, b, "Tajna")

    real = client.get(f"/people/{theirs}", headers=a.headers)
    invented = client.get("/people/per_does_not_exist_at_all", headers=a.headers)

    assert real.status_code == invented.status_code == 404
    assert real.json() == invented.json()
    assert "Tajna" not in real.text


def test_m03_qa_014_a_school_id_in_the_request_is_not_authority(
    db: Session, client: TestClient
) -> None:
    """§7: the tenant comes from the server-side context, never from the wire.

    Sent three ways — query, header and body — because a parameter is only
    ignored until some layer starts reading it, and the three layers read
    different places.
    """
    a, b = _two_tenants(db)
    theirs = _create_person(client, b, "Tudji")

    plain = client.get(f"/people/{theirs}", headers=a.headers)
    via_query = client.get(
        f"/people/{theirs}", params={"school_id": b.school.id}, headers=a.headers
    )
    via_header = client.get(
        f"/people/{theirs}",
        headers={**a.headers, "x-sokola-school-id": b.school.id},
    )
    assert plain.status_code == via_query.status_code == via_header.status_code == 404
    assert plain.json() == via_query.json() == via_header.json()

    # And a list request naming B still lists A.
    listed = client.get(
        "/people", params={"school_id": b.school.id}, headers=a.headers
    )
    assert listed.status_code == 200
    assert theirs not in {item["id"] for item in listed.json()["items"]}


def test_m03_qa_015_a_list_shows_only_this_tenants_rows_and_count(
    db: Session, client: TestClient
) -> None:
    """Three in A and seven in B. The `total` is the part worth asserting: a
    list that filtered its items but counted globally would look right on
    screen and still tell A exactly how many people B has."""
    a, b = _two_tenants(db)
    for n in range(2):
        _create_person(client, a, f"A{n}")
    for n in range(6):
        _create_person(client, b, f"B{n}")

    mine = client.get("/people", headers=a.headers).json()
    theirs = client.get("/people", headers=b.headers).json()
    assert mine["total"] == 3
    assert theirs["total"] == 7
    assert len(mine["items"]) == 3
    assert not any(item["display_name"].startswith("B") for item in mine["items"])


def test_m03_qa_016_a_report_counts_from_the_source_not_from_a_filtered_view(
    db: Session, client: TestClient
) -> None:
    """The same three-and-seven seed, read through an aggregate instead of a
    list. An aggregate is where a global count hides best: nothing about the
    number on screen says which rows it came from."""
    a, b = _two_tenants(db)
    for n in range(2):
        _create_person(client, a, f"A{n}")
    for n in range(6):
        _create_person(client, b, f"B{n}")

    mine = client.get("/reports/overview", headers=a.headers)
    theirs = client.get("/reports/overview", headers=b.headers)
    assert mine.status_code == theirs.status_code == 200
    assert mine.json()["active_member_count"] == 3
    assert theirs.json()["active_member_count"] == 7


def test_m03_qa_017_searching_for_someone_who_exists_only_elsewhere_finds_nothing(
    db: Session, client: TestClient
) -> None:
    """Equal to searching for a name nobody has. Search is the easiest place to
    confirm a guess — a result count of zero versus one answers "is there a
    Petrović at that other club" without ever returning a row."""
    a, b = _two_tenants(db)
    _create_person(client, b, "Jedinstvena")

    real = client.get("/search", params={"q": "Jedinstvena"}, headers=a.headers)
    nobody = client.get("/search", params={"q": "Nepostojeca"}, headers=a.headers)
    assert real.status_code == 200
    assert real.json()["results"] == []
    assert real.json()["results"] == nobody.json()["results"]


def test_m03_qa_019_a_write_cannot_reach_across_the_boundary_even_partially(
    db: Session, client: TestClient
) -> None:
    """Enrolling B's person into A's group. Refused, and — the half that
    matters — nothing is written: a guard that rejected after inserting the
    row would leave exactly the cross-tenant link it refused."""
    a, b = _two_tenants(db)
    theirs = _create_person(client, b, "Njihov")
    group = client.post("/groups", headers=a.headers, json={"name": "Delfini"})
    assert group.status_code == 201
    group_id = group.json()["id"]

    before = db.execute(text("SELECT count(*) FROM group_membership")).scalar_one()
    resp = client.post(
        f"/groups/{group_id}/members", headers=a.headers, json={"person_id": theirs}
    )
    assert resp.status_code == 404
    after = db.execute(text("SELECT count(*) FROM group_membership")).scalar_one()
    assert after == before


def test_m03_qa_020_a_mass_assigned_school_id_is_not_honoured(
    db: Session, client: TestClient
) -> None:
    """A create whose body names B. The person is created in A, and B never
    sees them — the DTO has no such field and the server uses its context."""
    a, b = _two_tenants(db)
    resp = client.post(
        "/people",
        headers=a.headers,
        json={
            "given_name": "Podmetnuta",
            "family_name": "Osoba",
            "school_id": b.school.id,
        },
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()["id"]

    assert created in {
        item["id"] for item in client.get("/people", headers=a.headers).json()["items"]
    }
    assert created not in {
        item["id"] for item in client.get("/people", headers=b.headers).json()["items"]
    }
    membership = db.execute(
        select(SchoolMembership.school_id).where(SchoolMembership.person_id == created)
    ).scalars().all()
    assert membership == [a.school.id]


def test_m03_qa_021_a_tenant_scoped_unique_key_is_unique_per_tenant(
    db: Session,
) -> None:
    """The same external reference in two schools is two facts, not a
    collision; the same one twice in one school is a collision.

    Both halves are needed. A unique index that forgot `school_id` would fail
    the first; one that was not unique at all would pass the first and fail
    the second, and only the pair distinguishes them.
    """
    a, b = _two_tenants(db)
    person_a = make_person(db, given="Ista", family="Sifra")
    person_b = make_person(db, given="Ista", family="Sifra2")
    add_membership(db, person=person_a, school=a.school)
    add_membership(db, person=person_b, school=b.school)

    for school, person in ((a.school, person_a), (b.school, person_b)):
        db.add(
            ExternalPersonReference(
                school_id=school.id,
                person_id=person.id,
                source="legacy",
                external_id="0001",
            )
        )
    db.commit()

    db.add(
        ExternalPersonReference(
            school_id=a.school.id,
            person_id=person_a.id,
            source="legacy",
            external_id="0001",
        )
    )
    with pytest.raises(IntegrityError) as raised:
        db.commit()
    assert "uq_external_person_ref" in str(raised.value)
    db.rollback()


def test_m03_qa_022_a_shared_person_shows_only_this_schools_local_data(
    db: Session, client: TestClient
) -> None:
    """One global `Person`, two memberships, two school-local codes. A's admin
    sees A's code and never B's — §2's "globalni Person" is a person, not a
    shared record."""
    a, b = _two_tenants(db)
    shared = make_person(db, given="Zajednicka", family="Osoba")
    add_membership(db, person=shared, school=a.school)
    add_membership(db, person=shared, school=b.school)

    assert (
        client.patch(
            f"/people/{shared.id}/membership",
            headers=a.headers,
            json={"local_member_code": "A-001", "admin_note": "beleska A"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/people/{shared.id}/membership",
            headers=b.headers,
            json={"local_member_code": "B-777", "admin_note": "beleska B"},
        ).status_code
        == 200
    )

    seen = client.get(f"/people/{shared.id}/membership", headers=a.headers)
    assert seen.status_code == 200
    assert seen.json()["local_member_code"] == "A-001"
    assert "B-777" not in seen.text
    assert "beleska B" not in seen.text


def test_m03_qa_023_one_organization_over_two_schools_grants_nothing(
    db: Session, client: TestClient
) -> None:
    """§2: the Organization is a legal holder, not a security boundary. Putting
    both schools under one is exactly the arrangement that tempts a reader to
    widen a query by organization, so the refusal is asserted *after* the
    transfer, not instead of it."""
    a, b = _two_tenants(db)
    holder_id = anchor.current_organization_link(db, a.school.id).organization_id
    holder = db.get(Organization, holder_id)
    anchor.transfer_organization(
        db,
        school_id=b.school.id,
        organization=holder,
        reason=OrganizationSchoolChangeReason.CORPORATE_RESTRUCTURE,
        case_reference="QA023",
        actor_ref="test",
    )
    db.commit()
    assert (
        anchor.current_organization_link(db, a.school.id).organization_id
        == anchor.current_organization_link(db, b.school.id).organization_id
    )

    theirs = _create_person(client, b, "Sestrinska")
    assert client.get(f"/people/{theirs}", headers=a.headers).status_code == 404


def test_m03_qa_025_another_tenants_document_streams_nothing(
    db: Session, client: TestClient
) -> None:
    """A download is the one place a tenant check is easy to put on the
    metadata read and forget on the bytes. Both are asked here: the metadata
    404s, and so does the content — with no body."""
    a, b = _two_tenants(db)
    uploaded = client.post(
        "/documents",
        headers=b.headers,
        files={"file": ("tajna.pdf", b"%PDF-1.4 poverljivo", "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]

    assert client.get(f"/documents/{document_id}", headers=a.headers).status_code == 404
    content = client.get(f"/documents/{document_id}/content", headers=a.headers)
    assert content.status_code == 404
    assert b"poverljivo" not in content.content


# ===========================================================================
# C. Switch, revoke i concurrency (§§9–10, 14–15)
# ===========================================================================


def test_m03_qa_028_two_tabs_at_the_same_version_produce_one_switch(
    db: Session,
) -> None:
    """§14's compare-and-swap. Two tabs read context version N and both try to
    switch — A→B and A→C — and exactly one lands.

    Driven sequentially rather than from two threads, and that is the honest
    description: what is proved here is the CAS contract, which is what makes
    the concurrent case safe. The lock that makes the interleaving safe is
    `SELECT ... FOR UPDATE` in `_locked`, and a same-process second connection
    would block on it rather than demonstrate anything.
    """
    person, account, session, _ = _signed_in(db, "sub-qa-028")
    a = make_school(db, name="Prva")
    b = make_school(db, name="Druga")
    c = make_school(db, name="Treca")
    for school in (a, b, c):
        _member_of(db, person, school, RoleCode.MANAGER)

    context = _select(db, session, account, a)
    version = context.context_version

    _select(db, session, account, b, expected=version)
    with pytest.raises(TenantSwitchConflictError):
        _select(db, session, account, c, expected=version)
    db.rollback()

    current = tenant_context.current(db, session.id)
    assert current.school_id == b.id
    assert current.context_version == version + 1
    assert (
        db.execute(
            select(func.count())
            .select_from(SessionTenantContext)
            .where(SessionTenantContext.session_id == session.id)
        ).scalar_one()
        == 1
    )


def test_m03_qa_031_a_suspended_membership_in_one_school_leaves_the_other(
    db: Session,
) -> None:
    """M06 suspends the A membership while the A screen is open. The next A
    request is refused and the context is invalidated — and B is still there
    to choose, because §9 invalidates a *context*, never the account."""
    person, account, session, _ = _signed_in(db, "sub-qa-031")
    a = make_school(db, name="Suspendovana")
    b = make_school(db, name="Netaknuta")
    _member_of(db, person, a, RoleCode.MANAGER)
    _member_of(db, person, b, RoleCode.MANAGER)
    context = _select(db, session, account, a)

    membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.school_id == a.id,
            SchoolMembership.person_id == person.id,
        )
    ).scalar_one()
    membership.status = MembershipStatus.SUSPENDED
    membership.suspension_reason_code = "QA031"
    db.commit()

    with pytest.raises(TenantContextNotAvailableError):
        tenant_context.resolve(
            db, context=context, account=account, person_id=person.id
        )
    refused = tenant_context.current(db, session.id)
    assert refused.status is TenantContextStatus.INVALIDATED
    assert refused.invalidation_reason_code is (
        ContextInvalidationReason.MEMBERSHIP_REVOKED
    )

    assert [item.school_id for item in _chooser(db, person, account).items] == [b.id]
    revived = _select(db, session, account, b)
    assert revived.status is TenantContextStatus.ACTIVE
    assert revived.school_id == b.id


def test_m03_qa_032_losing_the_role_behind_a_workspace_withdraws_the_option(
    db: Session,
) -> None:
    """The person keeps one role in A and loses the other. The chooser stops
    offering the workspace that role carried, and — the half a coordinator
    gets wrong — the surviving role's option and permissions are untouched."""
    person, account, _, _ = _signed_in(db, "sub-qa-032")
    school = make_school(db, name="Dve uloge")
    _member_of(db, person, school, RoleCode.PARENT, RoleCode.TRAINER)

    before = _chooser(db, person, account).items[0]
    assert {option.workspace_key for option in before.workspace_options} == {
        WORKSPACE_GUARDIAN,
        WORKSPACE_INSTRUCTOR,
    }

    assignment = db.execute(
        select(RoleAssignment).where(
            RoleAssignment.person_id == person.id,
            RoleAssignment.school_id == school.id,
            RoleAssignment.role_code == RoleCode.TRAINER,
        )
    ).scalar_one()
    assignment.status = RoleAssignmentStatus.REVOKED
    db.commit()

    after = _chooser(db, person, account).items
    assert len(after) == 1
    assert {option.workspace_key for option in after[0].workspace_options} == {
        WORKSPACE_GUARDIAN
    }
    assert effective_permissions(
        db, person_id=person.id, school_id=school.id
    ) == permissions_for_role_keys(db, role_keys=frozenset({"GUARDIAN"}))


def test_m03_qa_033_a_revoked_guardian_link_closes_the_child_immediately(
    db: Session, client: TestClient
) -> None:
    """M07 revokes one guardian link while the GUARDIAN screen is open.

    Three assertions, because a partial implementation passes any one of them:
    the child disappears from the list, the child's document stops
    downloading, and the guardian's *other* child is unaffected.
    """
    staff = bootstrap_actor(db, org_name="Roditeljska", given="Sef")
    guardian = add_actor(db, school=staff.school, role=RoleCode.PARENT, given="Roditelj")
    first = make_child_with_guardian(
        db, school=staff.school, guardian=guardian.person, given="Prvo"
    )
    second = make_child_with_guardian(
        db, school=staff.school, guardian=guardian.person, given="Drugo"
    )
    uploaded = client.post(
        "/documents",
        headers=staff.headers,
        files={"file": ("potvrda.pdf", b"%PDF-1.4 potvrda", "application/pdf")},
        data={"subject_person_id": first.id, "visibility": "SUBJECT"},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    assert (
        client.get(f"/documents/{document_id}/content", headers=guardian.headers).status_code
        == 200
    )

    link = db.execute(
        select(GuardianSchoolAccess).where(
            GuardianSchoolAccess.school_id == staff.school.id,
            GuardianSchoolAccess.guardian_person_id == guardian.person.id,
            GuardianSchoolAccess.child_person_id == first.id,
        )
    ).scalar_one()
    link.status = GuardianAccessStatus.REVOKED
    db.commit()

    listed = client.get("/parent/children", headers=guardian.headers)
    assert listed.status_code == 200
    assert [child["person_id"] for child in listed.json()] == [second.id]

    denied = client.get(f"/documents/{document_id}/content", headers=guardian.headers)
    assert denied.status_code in (403, 404)
    assert b"potvrda" not in denied.content


def test_m03_qa_035_the_guard_reads_authority_not_the_undelivered_event(
    db: Session,
) -> None:
    """A revoke is committed and the outbox message has not been delivered.

    The next request must already be refused. If the refusal waited on the
    consumer there would be a window — however short — in which a revoked
    person still worked, and §14 is explicit that the authoritative read is
    the guard and the event is only a projection signal.
    """
    person, account, session, _ = _signed_in(db, "sub-qa-035")
    school = make_school(db, name="Cvor A")
    _member_of(db, person, school, RoleCode.MANAGER)
    context = _select(db, session, account, school)

    tenant_security.invalidate(
        db,
        school.id,
        reason_code=TenantInvalidationReason.SECURITY_INCIDENT,
        correlation_id="qa-035",
    )
    db.commit()

    pending = db.execute(
        select(OutboxMessage).where(OutboxMessage.school_id == school.id)
    ).scalars().all()
    assert pending, "the invalidation must have produced an event to not rely on"
    assert all(message.status.value == "PENDING" for message in pending)

    with pytest.raises(TenantContextStaleError):
        tenant_context.resolve(
            db, context=context, account=account, person_id=person.id
        )


# ===========================================================================
# D. Outbox, schema i topologija (§§7.2, 11, 16)
# ===========================================================================

#: The one place §11 allows an outbox message with no tenant: M01's
#: account-wide authorization invalidation, which is about a person across
#: every school they belong to and therefore has no single `school_id` to
#: carry. Anything else with a null scope is a producer that forgot.
_PLATFORM_SCOPE_SITES = {"app/domains/identity/sessions.py"}


def _enqueue_sites() -> list[tuple[str, int, ast.Call]]:
    sites = []
    for py in sorted(Path("app").rglob("*.py")):
        for node in ast.walk(ast.parse(py.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "enqueue":
                sites.append((py.as_posix(), node.lineno, node))
    return sites


def test_m03_qa_043_no_outbox_event_leaves_its_tenant_to_a_default(
    db: Session, client: TestClient
) -> None:
    """§11: every tenant event carries `tenant_id=school_id`, and a platform
    event says so explicitly rather than arriving as `null` out of habit.

    `enqueue` defaults `school_id` to `None`, so "forgot the tenant" and
    "meant platform scope" are the same keystroke. The scan below removes that
    ambiguity at the call site — every producer must name the argument — and
    the allowlist makes the one genuine platform event a deliberate entry
    rather than an accident nobody notices.

    The runtime half then checks the other mismatch §2 names: a payload whose
    own `school_id` disagrees with the row's would route by one tenant and be
    read as another.
    """
    sites = _enqueue_sites()
    assert len(sites) > 30, f"expected the whole producer surface, found {len(sites)}"

    unnamed = [
        f"{path}:{line}"
        for path, line, call in sites
        if "school_id" not in {kw.arg for kw in call.keywords}
    ]
    assert not unnamed, f"enqueue without an explicit tenant decision: {unnamed}"

    null_scoped = [
        path
        for path, _, call in sites
        if any(
            kw.arg == "school_id"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is None
            for kw in call.keywords
        )
    ]
    assert set(null_scoped) <= _PLATFORM_SCOPE_SITES, sorted(
        set(null_scoped) - _PLATFORM_SCOPE_SITES
    )

    actor = bootstrap_actor(db, org_name="Proizvodjac", given="Sef")
    assert (
        client.post(
            "/people",
            headers=actor.headers,
            json={"given_name": "Nova", "family_name": "Osoba"},
        ).status_code
        == 201
    )
    messages = db.execute(select(OutboxMessage)).scalars().all()
    assert messages
    for message in messages:
        payload_school = message.payload.get("school_id")
        if payload_school is not None:
            assert payload_school == message.school_id, message.event_type


def test_m03_qa_048_the_database_refuses_a_cross_tenant_link_without_the_app(
    db: Session,
) -> None:
    """§7.2's composite foreign key, exercised by raw SQL with the application
    service bypassed entirely.

    A group in A and a person in B, wired together by hand. The insert names
    A's tenant, so the row is *internally* consistent — what rejects it is the
    four-column reference to `group`, which carries the tenant as part of the
    reference rather than beside it.
    """
    a, b = _two_tenants(db)
    theirs = make_person(db, given="Njihova", family="Osoba")
    add_membership(db, person=theirs, school=b.school)
    group = Group(school_id=a.school.id, name="Delfini")
    db.add(group)
    db.commit()
    group_id = group.id

    with pytest.raises(IntegrityError) as raised:
        db.execute(
            text(
                "INSERT INTO group_membership (id, group_id, school_id, person_id, "
                "role, joined_at, status, discount, created_at, updated_at) "
                "VALUES ('gmb_qa048', :group, :school, :person, 'MEMBER', now(), "
                "'ACTIVE', 0, now(), now())"
            ),
            {"group": group_id, "school": b.school.id, "person": theirs.id},
        )
        db.commit()
    assert "fk_group_membership_group_tenant" in str(raised.value)
    db.rollback()


def test_m03_qa_049_global_tables_carry_no_invented_school_id(db: Session) -> None:
    """§2: `Person` and `UserAccount` are global, and tenant access to them is
    proved by a membership or subject guard — never by a `school_id` column on
    the global table itself.

    A column like that reads as a tenant key and is not one: a person belongs
    to several schools, so whichever value it held would be wrong for all but
    one of them, and every query that trusted it would be quietly scoped to
    the wrong school.
    """
    columns = {
        table: {
            row[0]
            for row in db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t"
                ),
                {"t": table},
            )
        }
        for table in ("person", "user_account")
    }
    for table, names in columns.items():
        assert names, f"{table} is missing from the schema"
        assert "school_id" not in names, table

    # And the tenant-scoped tables that point at them do so with an ordinary
    # single-column foreign key, which is what §7.2 permits for a global target.
    referenced = db.execute(
        text(
            "SELECT c.conname, c.conrelid::regclass::text, array_length(c.conkey, 1) "
            "FROM pg_constraint c "
            "WHERE c.contype = 'f' AND c.confrelid = 'person'::regclass"
        )
    ).all()
    assert referenced, "nothing references person, so this proves nothing"
    assert all(width == 1 for _, _, width in referenced), [
        (name, table, width) for name, table, width in referenced if width != 1
    ]


def test_m03_qa_050_no_row_level_security_is_relied_on_or_silently_bypassed(
    db: Session,
) -> None:
    """§2's scenario is conditional — "ako repo koristi RLS" — and the honest
    answer is that it does not, so the pooled-connection leak it describes
    cannot happen here.

    The invariant asserted is the conjunction, not the premise: *either* no
    table relies on row level security, *or* the application role cannot
    bypass it. Asserting only the first would let someone add a policy to one
    table and believe it was enforced.

    It is enforced today by the empty left side, and that matters, because the
    right side is currently false: `compose.prod.yml` and CI both run the
    application as the `sokola` role created by the Postgres image's
    `POSTGRES_USER`, which is a database superuser — and a superuser bypasses
    every policy regardless of `rolbypassrls`. So the first RLS policy anyone
    writes would be dead on arrival, and this test is what would say so.
    Recorded as F-37.
    """
    protected = db.execute(
        text(
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity"
        )
    ).scalars().all()

    role = db.execute(
        text(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
    ).one()
    can_bypass = bool(role.rolsuper or role.rolbypassrls)

    assert not (protected and can_bypass), (
        f"row level security is relied on by {protected} while the application "
        "role bypasses it; see F-37"
    )
