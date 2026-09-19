"""TEN-Q02 `GetActiveTenantContext` (M03 §12, §6.1–6.3, §8).

Two things are being proved here.

The first is the query itself: it takes no input, it runs the whole §8
pipeline before answering, and what it returns is the tenant plus enough
version material to notice staleness — never a permission list, which §12
forbids as authority.

The second is a gap this closes. §6.2 says a school that is `IN_PREPARATION`
may give *only* a `SETUP_ONLY` context, and only to the authorized first
owner. The guard used to read the school's status solely to reject
`DEACTIVATED`, so an active membership in a school still being set up produced
an ordinary context for whoever held it.
"""

from __future__ import annotations

import pytest
from app.application.tenant_context import (
    context_etag,
    get_active_tenant_context,
)
from app.common.errors import (
    TenantContextNotAvailableError,
    TenantContextStaleError,
)
from app.domains.identity import sessions
from app.domains.identity.accounts import create_account_with_identity
from app.domains.identity.auth_enums import GOOGLE_ISSUER, GOOGLE_PROVIDER
from app.domains.identity.auth_models import AuthSession, UserAccount
from app.domains.identity.enums import RoleCode
from app.domains.identity.models import Person
from app.domains.school import ownership
from app.domains.school.enums import SchoolStatus
from app.domains.school.models import School
from app.domains.school.ownership_enums import OwnerNominationKind
from app.domains.tenancy import context as tenant_context
from app.domains.tenancy import security as tenant_security
from app.domains.tenancy.enums import (
    START_ROUTE_REGULAR,
    START_ROUTE_SETUP,
    WORKSPACE_ADMIN,
    SchoolMode,
    TenantInvalidationReason,
)
from app.domains.tenancy.models import SessionTenantContext
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.factories import add_membership, assign_role, make_person, make_school

SECRET = "test-secret"


def _signed_in(db: Session, subject: str) -> tuple[Person, UserAccount, AuthSession]:
    person = make_person(db, given="K", family=subject[-4:])
    account, identity = create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
    )
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    return person, account, session


def _selected(
    db: Session,
    person: Person,
    account: UserAccount,
    session: AuthSession,
    school: School,
) -> SessionTenantContext:
    add_membership(db, person=person, school=school)
    context = tenant_context.select_context(
        db,
        session=session,
        account=account,
        school=school,
        workspace_key=WORKSPACE_ADMIN,
    )
    db.commit()
    return context


def _ask(
    db: Session,
    context: SessionTenantContext,
    account: UserAccount,
    person: Person,
):
    return get_active_tenant_context(
        db, context=context, account=account, person_id=person.id, secret=SECRET
    )


def _make_primary_owner(db: Session, school: School, person: Person) -> None:
    """Give `person` the school's current primary owner term, the real way.

    Through the nomination + acceptance path rather than by inserting a term,
    because the term carries a four-column key back to an OWNER role
    assignment and a hand-made row would not satisfy it.
    """
    nomination = ownership.nominate_owner(
        db,
        school_id=school.id,
        person_id=person.id,
        kind=OwnerNominationKind.INITIAL_PRIMARY_OWNER,
        actor_ref="platform",
    )
    db.flush()
    assignment = assign_role(db, person=person, school=school, role=RoleCode.OWNER)
    ownership.fulfill_nomination(
        db, nomination=nomination, role_assignment=assignment, actor_ref="m02"
    )
    db.commit()


# ---------------------------------------------------------------------------
# The ordinary answer
# ---------------------------------------------------------------------------


def test_an_active_school_gives_a_regular_context(db: Session) -> None:
    person, account, session = _signed_in(db, "sub-regular")
    school = make_school(db, name="Radi")
    context = _selected(db, person, account, session, school)

    active = _ask(db, context, account, person)

    assert active.school_id == school.id
    assert active.school_mode is SchoolMode.REGULAR
    assert active.workspace_key == WORKSPACE_ADMIN
    assert active.context_version == context.context_version
    assert active.allowed_start_route == START_ROUTE_REGULAR
    assert active.context_etag


def test_the_result_carries_no_permission_list(db: Session) -> None:
    """§12: "Ne vraća permission listu kao autoritet."

    Asserted against the dataclass's own fields rather than a sample response,
    so adding one later fails here instead of quietly shipping.
    """
    person, account, session = _signed_in(db, "sub-thin")
    school = make_school(db)
    context = _selected(db, person, account, session, school)

    active = _ask(db, context, account, person)
    fields = set(active.__dataclass_fields__)

    assert fields == {
        "school_id",
        "school_mode",
        "workspace_key",
        "context_version",
        "context_etag",
        "allowed_start_route",
    }


# ---------------------------------------------------------------------------
# §6.2 — a school still being set up
# ---------------------------------------------------------------------------


def test_a_school_in_preparation_gives_setup_only_to_its_owner(db: Session) -> None:
    person, account, session = _signed_in(db, "sub-owner")
    school = make_school(db, name="Priprema", status=SchoolStatus.IN_PREPARATION)
    context = _selected(db, person, account, session, school)
    _make_primary_owner(db, school, person)

    active = _ask(db, context, account, person)

    assert active.school_mode is SchoolMode.SETUP_ONLY
    assert active.allowed_start_route == START_ROUTE_SETUP


def test_a_school_in_preparation_gives_nobody_else_anything(db: Session) -> None:
    """The gap this closes. A member of a school still being set up used to get
    an ordinary context — the status was read only to reject `DEACTIVATED`.

    §6.2 allows `IN_PREPARATION` to open setup for the first owner and nothing
    for anyone else. It is not a REGULAR context and it is not a SETUP_ONLY
    one either: a trainer has no business in the setup flow.
    """
    owner, owner_account, owner_session = _signed_in(db, "sub-own2")
    member, member_account, member_session = _signed_in(db, "sub-memb")
    school = make_school(db, name="Priprema", status=SchoolStatus.IN_PREPARATION)
    _selected(db, owner, owner_account, owner_session, school)
    _make_primary_owner(db, school, owner)
    member_context = _selected(db, member, member_account, member_session, school)

    with pytest.raises(TenantContextNotAvailableError):
        _ask(db, member_context, member_account, member)


def test_the_refusal_does_not_say_the_school_is_merely_unfinished(db: Session) -> None:
    """§11. The message is the same neutral one a missing school would get:
    "unavailable", never "exists, and is still being set up" — which would
    confirm a school id to someone who only guessed it."""
    person, account, session = _signed_in(db, "sub-neutral")
    school = make_school(db, status=SchoolStatus.IN_PREPARATION)
    context = _selected(db, person, account, session, school)

    with pytest.raises(TenantContextNotAvailableError) as raised:
        _ask(db, context, account, person)

    message = str(raised.value)
    assert "priprem" not in message.lower()
    assert "vlasni" not in message.lower()


# ---------------------------------------------------------------------------
# §8 — the pipeline still runs first
# ---------------------------------------------------------------------------


def test_a_stale_context_is_refused_and_invalidated(db: Session) -> None:
    """TEN-Q02 is not a shortcut around §8. A tenant-wide invalidation between
    selection and this call has to be noticed here too, and the row moves out
    of ACTIVE rather than merely being refused."""
    person, account, session = _signed_in(db, "sub-stale")
    school = make_school(db)
    context = _selected(db, person, account, session, school)

    tenant_security.invalidate(
        db, school.id, reason_code=TenantInvalidationReason.SECURITY_INCIDENT
    )
    db.commit()

    with pytest.raises(TenantContextStaleError):
        _ask(db, context, account, person)
    db.commit()

    assert not context.is_active


def test_a_terminated_membership_is_refused(db: Session) -> None:
    """§8 step 5 runs before any of this — the answer is not computed from a
    context row alone."""
    person, account, session = _signed_in(db, "sub-gone")
    school = make_school(db)
    context = _selected(db, person, account, session, school)

    db.execute(
        text(
            "UPDATE school_membership SET status = 'TERMINATED',"
            " termination_reason_code = 'LEFT', end_date = current_date"
            " WHERE school_id = :s AND person_id = :p"
        ),
        {"s": school.id, "p": person.id},
    )
    db.commit()

    with pytest.raises(TenantContextNotAvailableError):
        _ask(db, context, account, person)


# ---------------------------------------------------------------------------
# §5.4 — the etag
# ---------------------------------------------------------------------------


def test_the_etag_is_stable_for_an_unchanged_context(db: Session) -> None:
    person, account, session = _signed_in(db, "sub-etag1")
    school = make_school(db)
    context = _selected(db, person, account, session, school)

    assert _ask(db, context, account, person).context_etag == _ask(
        db, context, account, person
    ).context_etag


def test_the_etag_moves_when_tenant_access_is_invalidated(db: Session) -> None:
    """The reason the etag reads the *live* tenant access version rather than
    the one stored at selection: the stored one cannot change, so an etag built
    on it would stay fresh through exactly the invalidation it must report."""
    person, account, session = _signed_in(db, "sub-etag2")
    school = make_school(db)
    context = _selected(db, person, account, session, school)
    before = _ask(db, context, account, person).context_etag

    tenant_security.invalidate(
        db, school.id, reason_code=TenantInvalidationReason.SECURITY_INCIDENT
    )
    db.commit()

    after = context_etag(
        db,
        context=context,
        account=account,
        school=db.get(School, school.id),
        mode=SchoolMode.REGULAR,
        secret=SECRET,
    )
    assert after != before


def test_the_etag_is_keyed(db: Session) -> None:
    """Not a plain digest. The inputs are a school id, a workspace key and
    three small integers — a guessable space, so an unkeyed hash could be
    recomputed by a client to forge a current-looking etag, or compared to
    confirm a guess about another school's counters."""
    person, account, session = _signed_in(db, "sub-etag3")
    school = make_school(db)
    context = _selected(db, person, account, session, school)
    school_row = db.get(School, school.id)

    mine = context_etag(
        db,
        context=context,
        account=account,
        school=school_row,
        mode=SchoolMode.REGULAR,
        secret=SECRET,
    )
    theirs = context_etag(
        db,
        context=context,
        account=account,
        school=school_row,
        mode=SchoolMode.REGULAR,
        secret="a-different-deployment-secret",
    )
    assert mine != theirs


# ---------------------------------------------------------------------------
# The HTTP surface
# ---------------------------------------------------------------------------


def test_the_endpoint_takes_no_school_id(client: TestClient) -> None:
    """§12: the session comes only from the M01 credential.

    Read off the generated schema rather than by trying a request, because a
    parameter that is accepted and ignored looks identical from the outside
    until the day someone starts honouring it.
    """
    spec = client.get("/openapi.json").json()
    operation = spec["paths"]["/tenant/context"]["get"]
    assert operation.get("parameters", []) == []
    assert "requestBody" not in operation


def test_an_unauthenticated_caller_is_unauthorized_not_context_less(
    client: TestClient,
) -> None:
    """No credential at all is an M01 answer, not an M03 one.

    The principal dependency refuses first, so this never reaches the query —
    which is right: "choose a school" would imply there is a session to choose
    one for.
    """
    resp = client.get("/tenant/context")
    assert resp.status_code == 401


def test_a_signed_in_caller_with_no_selection_is_asked_to_choose(
    client: TestClient,
) -> None:
    """The neutral refusal that *is* shared: an authenticated caller who has
    not selected a school, and one whose selection went stale, get the same
    `TENANT_CONTEXT_REQUIRED`. Telling those two apart would leak whether a
    selection had ever been made."""
    # A real sign-in, so the cookie is signed the way production signs it.
    registered = client.post(
        "/auth/password/register",
        json={
            "email": "bez-izbora@example.com",
            "password": "longenough1",
            "given_name": "Bez",
            "family_name": "Izbora",
        },
    )
    assert registered.status_code == 200

    resp = client.get("/tenant/context")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "TENANT_CONTEXT_REQUIRED"
