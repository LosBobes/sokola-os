"""M03 §5.3, §8 step 3 and TEN-01/TEN-02: the session's school, and whether it holds.

A context is **a choice plus the moment it was made**, and every protected
request re-asks whether that moment is still now. Before this, there was no
stored moment — so there was no such thing as a stale context, only a context,
forever.

The three version snapshots are what §8 step 3 compares. None of them grants
anything (§5.3: "nije trajni allow dokaz"): they can make a context stale, never
make one sufficient. So every test below that moves a version asserts a
*refusal*, and the context is invalidated on the way out rather than merely
rejected — leaving it ACTIVE would make the next request rediscover the same
staleness.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import (
    TenantContextNotAvailableError,
    TenantContextStaleError,
    TenantSwitchConflictError,
)
from app.domains.identity import sessions
from app.domains.identity.accounts import create_account_with_identity
from app.domains.identity.auth_enums import GOOGLE_ISSUER, GOOGLE_PROVIDER
from app.domains.identity.auth_models import AuthIdentity, AuthSession, UserAccount
from app.domains.identity.models import Person
from app.domains.people import membership as membership_service
from app.domains.people import repository as people_repo
from app.domains.school.models import School
from app.domains.tenancy import context as tenant_context
from app.domains.tenancy import security as tenant_security
from app.domains.tenancy.enums import (
    WORKSPACE_ADMIN,
    WORKSPACE_INSTRUCTOR,
    ContextInvalidationReason,
    TenantContextStatus,
    TenantInvalidationReason,
)
from app.domains.tenancy.models import SessionTenantContext
from app.platform import clock
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import add_membership, make_person, make_school


def _identity_of(db: Session, account: UserAccount) -> AuthIdentity:
    """The account's linked identity — a second session needs one to hang off."""
    return db.execute(
        select(AuthIdentity).where(AuthIdentity.user_account_id == account.id)
    ).scalars().first()


def _signed_in(
    db: Session, subject: str = "sub-ctx"
) -> tuple[Person, UserAccount, AuthSession]:
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


def _member_of(db: Session, person: Person, name: str = "Klub") -> School:
    school = make_school(db, name=name)
    add_membership(db, person=person, school=school)
    db.commit()
    return school


def _select(
    db: Session,
    person: Person,
    account: UserAccount,
    session: AuthSession,
    school: School,
    **kwargs: object,
) -> SessionTenantContext:
    context = tenant_context.select_context(
        db,
        session=session,
        account=account,
        school=school,
        workspace_key=str(kwargs.pop("workspace_key", WORKSPACE_ADMIN)),
        **kwargs,  # type: ignore[arg-type]
    )
    db.commit()
    return context


# ---------------------------------------------------------------------------
# §5.3 — the row
# ---------------------------------------------------------------------------


def test_selection_snapshots_all_three_versions(db: Session) -> None:
    """The snapshots are the reason the table exists: without a recorded moment
    of selection there is nothing for §8 step 3 to compare against."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    context = _select(db, person, account, session, school)

    assert context.context_version == 1
    assert context.authorization_version_at_selection == account.authorization_version
    assert context.tenant_access_version_at_selection == tenant_security.current_version(
        db, school.id
    )
    assert context.status is TenantContextStatus.ACTIVE


def test_one_context_per_session(db: Session) -> None:
    """§5.3: at most one current row. Two would be two answers to "which school
    is this session in"."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    _select(db, person, account, session, school)

    db.add(
        SessionTenantContext(
            session_id=session.id,
            user_account_id=account.id,
            school_id=school.id,
            workspace_key=WORKSPACE_ADMIN,
            context_version=1,
            tenant_access_version_at_selection=1,
            authorization_version_at_selection=1,
            selected_at=clock.now(),
            last_validated_at=clock.now(),
            version=1,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_an_active_context_carries_no_invalidation_stamp(db: Session) -> None:
    """§5.3's paired CHECK. A context that ended without a recorded reason is
    the one a security review most needs and least often gets."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    context = _select(db, person, account, session, school)
    context.invalidated_at = clock.now()
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_the_context_holds_no_permissions(db: Session) -> None:
    """§5.3: no permission list, no guardian scope, no financial subject, no
    copy of tenant data. The strongest form of that is having nowhere to put
    them."""
    from sqlalchemy import inspect

    columns = {c.name for c in inspect(SessionTenantContext).columns}
    assert columns & {
        "permissions",
        "granted_areas",
        "role_code",
        "role_assignment_id",
        "guardian_scope",
        "subject_scope",
        "payer_id",
    } == set()


def test_an_unregistered_workspace_key_is_refused(db: Session) -> None:
    """§5.3: the key comes from a closed display registry. One we have no
    screen for is a client sending something we cannot render."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    with pytest.raises(TenantContextNotAvailableError):
        _select(db, person, account, session, school, workspace_key="SUPERUSER")


# ---------------------------------------------------------------------------
# TEN-01 — select and switch
# ---------------------------------------------------------------------------


def test_switching_school_reuses_the_row_and_moves_the_version(db: Session) -> None:
    """§9: a switch is an increment, not an insert — which is what lets a
    response still in flight for school A be recognised as belonging to a
    context that no longer exists."""
    person, account, session = _signed_in(db)
    first = _member_of(db, person, "Prva")
    second = _member_of(db, person, "Druga")

    context = _select(db, person, account, session, first)
    assert context.context_version == 1

    switched = _select(db, person, account, session, second)
    assert switched.id == context.id
    assert switched.school_id == second.id
    assert switched.context_version == 2


def test_a_stale_expected_version_loses_the_switch(db: Session) -> None:
    """§14: two tabs with the same expected version — exactly one wins, and the
    loser is told rather than silently overwritten. A person acting in a school
    they can see they did not choose is the failure being avoided."""
    person, account, session = _signed_in(db)
    first = _member_of(db, person, "Prva")
    second = _member_of(db, person, "Druga")
    third = _member_of(db, person, "Treca")

    context = _select(db, person, account, session, first)
    stale_version = context.context_version

    _select(db, person, account, session, second, expected_context_version=stale_version)
    db.commit()

    with pytest.raises(TenantSwitchConflictError):
        _select(
            db, person, account, session, third, expected_context_version=stale_version
        )


def test_an_invalidated_context_can_be_chosen_again(db: Session) -> None:
    """§9: `INVALIDATED` → `ACTIVE` on a fresh, fully valid selection. The same
    row gains a new revision; the previous history stays in the audit."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    context = _select(db, person, account, session, school)
    tenant_context.clear_context(db, session_id=session.id)
    db.commit()
    assert context.status is TenantContextStatus.INVALIDATED

    revived = _select(db, person, account, session, school)
    assert revived.id == context.id
    assert revived.status is TenantContextStatus.ACTIVE
    assert revived.invalidated_at is None
    assert revived.context_version >= 3


# ---------------------------------------------------------------------------
# TEN-02 — clear
# ---------------------------------------------------------------------------


def test_clearing_keeps_the_session(db: Session) -> None:
    """§9: clearing a context is "I am done with this school", not "log me
    out". Conflating them makes leaving a school cost a person their session."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    _select(db, person, account, session, school)

    tenant_context.clear_context(db, session_id=session.id)
    db.commit()

    db.refresh(session)
    assert session.revoked_at is None
    assert tenant_context.current(db, session.id).status is TenantContextStatus.INVALIDATED


def test_clearing_twice_keeps_the_first_reason(db: Session) -> None:
    """§9: "identičan retry već izvršene invalidacije" returns the original and
    does not move the version again — a retry that bumped the counter would put
    a second invalidation in the history that never happened."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    _select(db, person, account, session, school)

    first = tenant_context.clear_context(db, session_id=session.id)
    db.commit()
    version_after = first.context_version

    again = tenant_context.clear_context(
        db,
        session_id=session.id,
        reason=ContextInvalidationReason.SESSION_ENDED,
    )
    db.commit()
    assert again.invalidation_reason_code is ContextInvalidationReason.USER_CLEARED
    assert again.context_version == version_after


def test_clearing_a_session_with_no_context_is_a_no_op(db: Session) -> None:
    _, _, session = _signed_in(db)
    assert tenant_context.clear_context(db, session_id=session.id) is None


# ---------------------------------------------------------------------------
# §8 step 3 — the comparisons
# ---------------------------------------------------------------------------


def test_a_valid_context_resolves(db: Session) -> None:
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    context = _select(db, person, account, session, school)

    resolved = tenant_context.resolve(
        db, context=context, account=account, person_id=person.id
    )
    assert resolved.id == school.id


def test_an_account_version_bump_invalidates_the_context(db: Session) -> None:
    """M01's version moved, so the account's access changed after this context
    was chosen. §8 step 3 refuses; §9 moves the row out of ACTIVE."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    context = _select(db, person, account, session, school)

    account.authorization_version += 1
    db.commit()

    with pytest.raises(TenantContextStaleError):
        tenant_context.resolve(
            db, context=context, account=account, person_id=person.id
        )
    assert context.status is TenantContextStatus.INVALIDATED
    assert context.invalidation_reason_code is ContextInvalidationReason.CONTEXT_STALE


def test_a_tenant_invalidation_invalidates_the_context(db: Session) -> None:
    """M03's own version, moved by TEN-04. This is the path a whole school's
    access uses, and it reaches an open session without touching its row."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    context = _select(db, person, account, session, school)

    tenant_security.invalidate(
        db, school.id, reason_code=TenantInvalidationReason.SECURITY_INCIDENT
    )
    db.commit()

    with pytest.raises(TenantContextStaleError):
        tenant_context.resolve(
            db, context=context, account=account, person_id=person.id
        )
    assert context.invalidation_reason_code is (
        ContextInvalidationReason.TENANT_ACCESS_INVALIDATED
    )


def test_a_revoked_membership_closes_the_context(db: Session) -> None:
    """§6.1 point 4 and §8 step 5: membership evidence is re-proved, never
    remembered. The role assignment is irrelevant here — this is the other
    half of §6.1, and it has to be checked separately because the two are
    revoked by different people at different times."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    context = _select(db, person, account, session, school)

    membership = people_repo.get_membership(db, school.id, person.id)
    membership_service.terminate_membership(db, membership, reason_code="LEFT_SCHOOL")
    db.commit()

    with pytest.raises(TenantContextNotAvailableError):
        tenant_context.resolve(
            db, context=context, account=account, person_id=person.id
        )
    assert context.invalidation_reason_code is (
        ContextInvalidationReason.MEMBERSHIP_REVOKED
    )


def test_an_already_invalidated_context_stays_refused(db: Session) -> None:
    """§9: nothing revives on its own. A new selection is a deliberate act."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    context = _select(db, person, account, session, school)
    tenant_context.clear_context(db, session_id=session.id)
    db.commit()

    with pytest.raises(TenantContextStaleError):
        tenant_context.resolve(
            db, context=context, account=account, person_id=person.id
        )


def test_resolving_records_the_check_without_excusing_the_next_one(
    db: Session,
) -> None:
    """§5.3: `last_validated_at` "ne dozvoljava preskakanje nove provere".
    Writing down that a check happened must not buy the next request out of
    doing it — so a bump right after a successful resolve still refuses."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    context = _select(db, person, account, session, school)

    later = clock.now() + dt.timedelta(minutes=1)
    tenant_context.resolve(
        db, context=context, account=account, person_id=person.id, now=later
    )
    assert context.last_validated_at == later

    account.authorization_version += 1
    db.commit()
    with pytest.raises(TenantContextStaleError):
        tenant_context.resolve(
            db, context=context, account=account, person_id=person.id
        )


def test_one_sessions_choice_does_not_move_another(db: Session) -> None:
    """§5.3: "izbor u jednoj sesiji ne menja aktivni kontekst druge sesije istog
    naloga". Two browsers, two schools, at once."""
    person, account, first_session = _signed_in(db, "sub-two-sessions")
    school_a = _member_of(db, person, "Alfa")
    school_b = _member_of(db, person, "Beta")
    identity_session, _ = sessions.issue_session(
        db, account=account, identity=_identity_of(db, account)
    )
    db.commit()

    _select(db, person, account, first_session, school_a)
    _select(db, person, account, identity_session, school_b)

    assert tenant_context.current(db, first_session.id).school_id == school_a.id
    assert tenant_context.current(db, identity_session.id).school_id == school_b.id


def test_the_workspace_key_is_display_only(db: Session) -> None:
    """§3: "Nije role assignment, permission filter niti authorization dokaz."
    Changing it changes the recorded focus and nothing about what resolves."""
    person, account, session = _signed_in(db)
    school = _member_of(db, person)
    _select(db, person, account, session, school, workspace_key=WORKSPACE_ADMIN)
    switched = _select(
        db, person, account, session, school, workspace_key=WORKSPACE_INSTRUCTOR
    )
    assert switched.workspace_key == WORKSPACE_INSTRUCTOR

    resolved = tenant_context.resolve(
        db, context=switched, account=account, person_id=person.id
    )
    assert resolved.id == school.id
