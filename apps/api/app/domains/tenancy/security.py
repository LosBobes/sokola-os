"""M03 TEN-04/TEN-05: establishing and invalidating a school's access.

Named `security` rather than `service` on purpose: the architecture gate stops
one domain importing another's `service`, and M04 provisioning has to call
`initialize` in the *same transaction* as creating the school (§5.5 / TEN-05).
A port that has to be reachable is not a layering violation dressed up — it is
why the gate's list names `service`, `repository`, `router` and `policy` rather
than "anything".

Neither function commits. §14 wants the version bump atomic with the M04 status
change it accompanies, and a function that committed for itself would take that
decision away from the caller that owns the transaction.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.common.errors import NotFoundError
from app.domains.tenancy.enums import (
    SCHOOL_ACCESS_INVALIDATED_EVENT,
    TenantInvalidationReason,
)
from app.domains.tenancy.models import TenantSecurityState
from app.platform import clock
from app.platform.outbox.service import enqueue


def initialize(db: Session, school_id: str) -> TenantSecurityState:
    """TEN-05. Idempotently give a school its security state.

    Idempotent because §5.5 requires this in the same transaction as tenant
    provisioning *or* "strogo ekvivalentnim recovery ugovorom" — and a recovery
    path that could only run once would be no recovery at all. A school that
    already has a state keeps it, version and all.

    Grants nothing: not membership, not a role, not a subscription, not access.
    It establishes the clock a later invalidation moves.
    """
    existing = db.get(TenantSecurityState, school_id)
    if existing is not None:
        return existing
    state = TenantSecurityState(
        school_id=school_id, tenant_access_version=1, version=1
    )
    db.add(state)
    db.flush()
    return state


def current_version(db: Session, school_id: str) -> int:
    """The school's access version, for a guard to compare a context against.

    A missing row is an error rather than a default: §5.2 says every school has
    exactly one, so its absence means provisioning did not finish, and reading
    that as "version 1, carry on" would be the fail-open reading of a broken
    invariant.
    """
    version = db.execute(
        select(TenantSecurityState.tenant_access_version).where(
            TenantSecurityState.school_id == school_id
        )
    ).scalar_one_or_none()
    if version is None:
        raise NotFoundError("Bezbednosno stanje škole nije dostupno.")
    return int(version)


def invalidate(
    db: Session,
    school_id: str,
    *,
    reason_code: TenantInvalidationReason,
    correlation_id: str | None = None,
    now: dt.datetime | None = None,
) -> TenantSecurityState:
    """TEN-04. Make everything issued before this moment stale, at once.

    Locks the row first, because two concurrent invalidations that both read
    version N and both write N+1 would lose one bump — and a lost bump means
    one set of contexts silently survived an invalidation that reported success.

    The outbox event closes realtime channels and rebuilds secondary
    projections. It is not the guard: §14 requires the next request to be
    refused by an authoritative version/status read, and TEN-04's own wording is
    that it "ne mora sinhrono update-ovati svaki session red da bi bio bezbedan"
    precisely because the comparison happens on read.
    """
    moment = now or clock.now()
    _lock(db, school_id)
    state = db.get(TenantSecurityState, school_id)
    if state is None:
        raise NotFoundError("Bezbednosno stanje škole nije dostupno.")
    db.refresh(state)

    state.tenant_access_version += 1
    state.version += 1
    state.last_invalidated_at = moment
    state.last_invalidation_reason_code = reason_code

    # §11: a tenant event carries `tenant_id=school_id`. Unlike M01's
    # account-wide invalidation, this one has exactly one school by definition,
    # so there is nothing to fan out and no reason to reach for platform scope.
    enqueue(
        db,
        event_type=SCHOOL_ACCESS_INVALIDATED_EVENT,
        payload={
            "school_id": school_id,
            "tenant_access_version": state.tenant_access_version,
            "reason_code": reason_code.value,
            "correlation_id": correlation_id,
            "dedupe_key": f"{school_id}:{state.tenant_access_version}",
        },
        school_id=school_id,
    )
    db.flush()
    return state


def _lock(db: Session, school_id: str) -> None:
    db.execute(
        text("SELECT 1 FROM tenant_security_state WHERE school_id = :id FOR UPDATE"),
        {"id": school_id},
    )
