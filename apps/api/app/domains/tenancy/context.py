"""M03 §5.3, §8 and TEN-01/TEN-02: the session's current school, and whether it
still holds.

The whole module is one idea: **a context is a choice plus the moment it was
made**, and every protected request re-asks whether that moment is still now.

§8 lists ten steps. Three of them are version comparisons (step 3), and they
are what this file exists for. Each compares a snapshot taken at selection
against its live authority:

* ``context_version`` — this session's own select/switch/clear counter, so a
  slow response from school A cannot commit after a switch to B (§10);
* ``tenant_access_version`` — M03's, moved when a whole school's access is
  invalidated;
* ``authorization_version`` — M01's, moved when the account's is.

None of the three grants anything. §5.3: "nije trajni allow dokaz". They can
make a context stale, never make one sufficient — which is why a stale context
is *invalidated* here and the request refused, rather than quietly refreshed.

M05 and M07 are not called from here. §8 puts their guards *after* this one in
the application pipeline, and §2 says M03 must not import them; a tenant module
that decided permissions would be a second permission owner.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.errors import (
    TenantContextNotAvailableError,
    TenantContextStaleError,
    TenantSwitchConflictError,
)
from app.domains.identity.auth_models import AuthSession, UserAccount
from app.domains.school.enums import MembershipStatus, SchoolStatus
from app.domains.school.models import School, SchoolMembership
from app.domains.tenancy import security as tenant_security
from app.domains.tenancy.enums import (
    WORKSPACE_KEYS,
    ContextInvalidationReason,
    TenantContextStatus,
)
from app.domains.tenancy.models import SessionTenantContext, TenantContextUsage
from app.platform import clock


def current(db: Session, session_id: str) -> SessionTenantContext | None:
    """This session's context row, whatever state it is in.

    An ``INVALIDATED`` row is returned rather than hidden: §9 lets the same row
    come back to ``ACTIVE`` on a fresh selection, and the caller needs to see
    what it is reviving.
    """
    return db.execute(
        select(SessionTenantContext).where(SessionTenantContext.session_id == session_id)
    ).scalar_one_or_none()


def select_context(
    db: Session,
    *,
    session: AuthSession,
    account: UserAccount,
    school: School,
    workspace_key: str,
    expected_context_version: int | None = None,
    now: dt.datetime | None = None,
) -> SessionTenantContext:
    """TEN-01. Choose or switch this session's school, atomically.

    ``expected_context_version`` is the compare-and-swap §14 asks for: two tabs
    holding the same version means exactly one switch wins and the other is
    told, rather than both writing and the later one silently deciding. It is
    optional only because the first selection has no version to expect.

    The row is reused rather than replaced — §5.3 wants at most one per session
    and §9 lets an invalidated one return to ``ACTIVE`` with a new revision, so
    a switch is an increment, not an insert.

    What this deliberately does not do is decide whether the choice is allowed.
    §8 puts membership, permission and subject guards around this, and a
    function that both recorded and authorized a choice would be the one place
    nobody could audit.
    """
    if workspace_key not in WORKSPACE_KEYS:
        # §5.3: the key must come from the closed display registry. An
        # unrecognised one is a client sending something we have no screen for.
        raise TenantContextNotAvailableError("Traženi prikaz nije dostupan.")

    moment = now or clock.now()
    existing = _locked(db, session.id)

    if (
        existing is not None
        and expected_context_version is not None
        and existing.context_version != expected_context_version
    ):
        raise TenantSwitchConflictError(
            "Kontekst je u međuvremenu promenjen. Osvežite i pokušajte ponovo."
        )

    tenant_version = tenant_security.current_version(db, school.id)
    if existing is None:
        context = SessionTenantContext(
            session_id=session.id,
            user_account_id=account.id,
            school_id=school.id,
            workspace_key=workspace_key,
            status=TenantContextStatus.ACTIVE,
            context_version=1,
            tenant_access_version_at_selection=tenant_version,
            authorization_version_at_selection=account.authorization_version,
            selected_at=moment,
            last_validated_at=moment,
            version=1,
        )
        db.add(context)
        _record_usage(db, account=account, school=school, workspace_key=workspace_key, now=moment)
        db.flush()
        return context

    existing.school_id = school.id
    existing.workspace_key = workspace_key
    existing.user_account_id = account.id
    existing.status = TenantContextStatus.ACTIVE
    existing.invalidated_at = None
    existing.invalidation_reason_code = None
    existing.tenant_access_version_at_selection = tenant_version
    existing.authorization_version_at_selection = account.authorization_version
    existing.selected_at = moment
    existing.last_validated_at = moment
    existing.context_version += 1
    existing.version += 1
    _record_usage(db, account=account, school=school, workspace_key=workspace_key, now=moment)
    db.flush()
    return existing


def _record_usage(
    db: Session,
    *,
    account: UserAccount,
    school: School,
    workspace_key: str,
    now: dt.datetime,
) -> None:
    """Remember that this account was here, for the chooser's benefit only.

    Written on selection rather than on every request: §12 sorts by *last
    valid use*, and a selection is exactly that moment — the point where §8
    has just proved the choice is allowed. Updating it per request would turn
    a display hint into a write on the hot path for no gain.

    Deliberately after the context row, and in the same transaction: if the
    selection fails, there is nothing to remember.
    """
    usage = db.get(TenantContextUsage, (account.id, school.id))
    if usage is None:
        db.add(
            TenantContextUsage(
                user_account_id=account.id,
                school_id=school.id,
                last_used_at=now,
                last_workspace_key=workspace_key,
            )
        )
        return
    usage.last_used_at = now
    usage.last_workspace_key = workspace_key


def clear_context(
    db: Session,
    *,
    session_id: str,
    reason: ContextInvalidationReason = ContextInvalidationReason.USER_CLEARED,
    now: dt.datetime | None = None,
) -> SessionTenantContext | None:
    """TEN-02. Drop this session's school choice, keeping the session.

    Idempotent, per §9's "identičan retry već izvršene invalidacije": an
    already-invalidated context keeps its original reason and does **not**
    bump the version again. The first invalidation is the one that happened,
    and a retry that moved the counter would make a second one appear in the
    history.

    The M01 session is untouched. Clearing a context is "I am done with this
    school", not "log me out" — §9 keeps those separate because conflating
    them makes leaving a school cost a person their whole session.
    """
    context = _locked(db, session_id)
    if context is None or context.status is TenantContextStatus.INVALIDATED:
        return context
    return _invalidate(db, context, reason=reason, now=now)


def resolve(
    db: Session,
    *,
    context: SessionTenantContext,
    account: UserAccount,
    person_id: str,
    now: dt.datetime | None = None,
) -> School:
    """§8 steps 3–5, in order, fail-closed at each.

    Returns the school this context may act in, or raises. A stale context is
    invalidated on the way out rather than merely refused: §9 moves it out of
    ``ACTIVE`` on a version mismatch, and leaving it active would mean the next
    request has to rediscover the same staleness.

    The membership re-proof (step 5) is the one that most often gets skipped in
    practice, because a role assignment looks like enough. It is not: §6.1
    requires *both* an active assignment and current M06 `ACTIVE` membership
    evidence, and §6.1 adds that `DRAFT`, `SUSPENDED` and `TERMINATED`
    membership give no regular access at all.
    """
    moment = now or clock.now()
    if context.status is not TenantContextStatus.ACTIVE:
        raise TenantContextStaleError("Potreban je ponovni izbor škole.")

    # Step 3a — M01's authorization version. A revoked account fails here even
    # if its session row somehow survived.
    if context.authorization_version_at_selection != account.authorization_version:
        _invalidate(db, context, reason=ContextInvalidationReason.CONTEXT_STALE, now=moment)
        raise TenantContextStaleError("Bezbednosno stanje naloga se promenilo.")

    # Step 4 — the school's live status, read every time. §5.2 keeps this
    # mandatory alongside the version: the version says "something changed",
    # the status says "this is what it is now".
    school = db.get(School, context.school_id)
    if school is None or school.status is SchoolStatus.DEACTIVATED:
        _invalidate(
            db, context, reason=ContextInvalidationReason.SCHOOL_UNAVAILABLE, now=moment
        )
        raise TenantContextNotAvailableError("Škola nije dostupna.")

    # Step 3b — M03's tenant access version.
    if context.tenant_access_version_at_selection != tenant_security.current_version(
        db, school.id
    ):
        _invalidate(
            db,
            context,
            reason=ContextInvalidationReason.TENANT_ACCESS_INVALIDATED,
            now=moment,
        )
        raise TenantContextStaleError("Pristup školi je u međuvremenu osvežen.")

    # Step 5 — M06 membership evidence, re-proved rather than remembered.
    if not has_active_membership(db, school_id=school.id, person_id=person_id):
        _invalidate(
            db, context, reason=ContextInvalidationReason.MEMBERSHIP_REVOKED, now=moment
        )
        raise TenantContextNotAvailableError("Nemate aktivan pristup ovoj školi.")

    context.last_validated_at = moment
    return school


def has_active_membership(db: Session, *, school_id: str, person_id: str) -> bool:
    """§6.1 point 4: current M06 membership evidence with status `ACTIVE`.

    Membership evidence is not a role (§3). This answers "does this person
    belong to this school right now" and nothing about what they may do there.
    """
    return (
        db.execute(
            select(SchoolMembership.id).where(
                SchoolMembership.school_id == school_id,
                SchoolMembership.person_id == person_id,
                SchoolMembership.status == MembershipStatus.ACTIVE,
                SchoolMembership.record_status == RecordStatus.ACTIVE,
            )
        ).first()
        is not None
    )


def _invalidate(
    db: Session,
    context: SessionTenantContext,
    *,
    reason: ContextInvalidationReason,
    now: dt.datetime | None = None,
) -> SessionTenantContext:
    moment = now or clock.now()
    context.status = TenantContextStatus.INVALIDATED
    context.invalidated_at = moment
    context.invalidation_reason_code = reason
    context.context_version += 1
    context.version += 1
    db.flush()
    return context


def _locked(db: Session, session_id: str) -> SessionTenantContext | None:
    """Lock the session's context row before reading it for a change.

    §14 wants select/switch to lock the parent row or use an equivalent
    compare-and-swap. Without it, two tabs can both read version N and both
    write N+1, and the loser's school silently becomes the winner's.
    """
    db.execute(
        text("SELECT 1 FROM session_tenant_context WHERE session_id = :sid FOR UPDATE"),
        {"sid": session_id},
    )
    return current(db, session_id)
