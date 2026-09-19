"""M03 §5.2, TEN-04 and TEN-05: a school's access, as a thing that can go stale.

`School.status` already takes effect immediately, because the request guard
re-reads it every time. That is real and it is not what this adds. A status
column cannot express "everything issued before this moment is now suspect" —
that needs a monotone number a cached context, a secondary projection or an
open channel can be compared against and found old.

The outbox event exists (§15) but is not the guard. §14 requires the next
request to be refused by an authoritative version/status read, which is why
TEN-04 can say it "ne mora sinhrono update-ovati svaki session red da bi bio
bezbedan": the comparison happens on read.
"""

from __future__ import annotations

import pytest
from app.common.errors import ConflictError, NotFoundError
from app.domains.school import anchor
from app.domains.school.enums import SchoolStatus, SchoolStatusReason
from app.domains.school.models import School
from app.domains.tenancy import security as tenancy
from app.domains.tenancy.enums import (
    SCHOOL_ACCESS_INVALIDATED_EVENT,
    TenantInvalidationReason,
)
from app.domains.tenancy.models import TenantSecurityState
from app.platform import clock
from app.platform.outbox.models import OutboxMessage
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import make_school


def _provisioned(db: Session, **kwargs: object) -> School:
    """A school created the way provisioning creates one.

    `make_school` already runs the full M04 anchor including `record_creation`,
    which is where TEN-05 now hangs — so every school a test makes proves the
    wiring, not just the ones that ask for it.
    """
    school = make_school(db, **kwargs)  # type: ignore[arg-type]
    db.commit()
    return school


# ---------------------------------------------------------------------------
# TEN-05 — the state exists with the school
# ---------------------------------------------------------------------------


def test_a_new_school_gets_a_security_state(db: Session) -> None:
    """§5.5: established in the same transaction as provisioning. A school that
    existed for even one commit without one would be a school whose access
    version nothing could compare against."""
    school = _provisioned(db)
    state = db.get(TenantSecurityState, school.id)
    assert state is not None
    assert state.tenant_access_version == 1
    assert state.version == 1
    assert state.last_invalidated_at is None


def test_initialize_is_idempotent(db: Session) -> None:
    """§5.5 allows a "strogo ekvivalentan recovery ugovor", and a recovery path
    that could only run once would be no recovery at all."""
    school = _provisioned(db)
    tenancy.invalidate(
        db, school.id, reason_code=TenantInvalidationReason.SECURITY_INCIDENT
    )
    db.commit()
    bumped = tenancy.current_version(db, school.id)

    again = tenancy.initialize(db, school.id)
    db.commit()
    assert again.tenant_access_version == bumped, "re-initialising reset the clock"


def test_exactly_one_state_per_school(db: Session) -> None:
    """§5.2 says 1:1. A second row would be a second answer to a question that
    must have one."""
    school = _provisioned(db)
    db.add(TenantSecurityState(school_id=school.id, tenant_access_version=1, version=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_missing_state_is_an_error_not_a_default(db: Session) -> None:
    """Reading absence as "version 1, carry on" would be the fail-open reading
    of a broken invariant."""
    school = make_school(db)
    db.commit()
    db.execute(
        text("DELETE FROM tenant_security_state WHERE school_id = :id"),
        {"id": school.id},
    )
    db.commit()
    with pytest.raises(NotFoundError):
        tenancy.current_version(db, school.id)


# ---------------------------------------------------------------------------
# §5.2 — the row's own contract
# ---------------------------------------------------------------------------


def test_the_invalidation_stamp_and_reason_travel_together(db: Session) -> None:
    """A reason without a time (or the reverse) is a half-written invalidation,
    and the reason is the only part that survives into the audit trail."""
    school = _provisioned(db)
    state = db.get(TenantSecurityState, school.id)
    state.last_invalidated_at = clock.now()
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_the_access_version_cannot_start_below_one(db: Session) -> None:
    school = make_school(db)
    db.commit()
    db.execute(
        text("DELETE FROM tenant_security_state WHERE school_id = :id"),
        {"id": school.id},
    )
    db.add(TenantSecurityState(school_id=school.id, tenant_access_version=0, version=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# TEN-04 — invalidation
# ---------------------------------------------------------------------------


def test_invalidation_moves_the_version_by_one(db: Session) -> None:
    school = _provisioned(db)
    before = tenancy.current_version(db, school.id)

    state = tenancy.invalidate(
        db, school.id, reason_code=TenantInvalidationReason.SECURITY_INCIDENT
    )
    db.commit()

    assert state.tenant_access_version == before + 1
    assert state.last_invalidation_reason_code is (
        TenantInvalidationReason.SECURITY_INCIDENT
    )
    assert state.last_invalidated_at is not None


def test_the_version_only_ever_goes_up(db: Session) -> None:
    """Monotone, because everything downstream decides "older than this" by
    comparing — and a number that could go backwards would make something old
    look current."""
    school = _provisioned(db)
    seen = [tenancy.current_version(db, school.id)]
    for reason in (
        TenantInvalidationReason.SECURITY_INCIDENT,
        TenantInvalidationReason.OWNERSHIP_TRANSFERRED,
        TenantInvalidationReason.PLATFORM_POLICY,
    ):
        tenancy.invalidate(db, school.id, reason_code=reason)
        db.commit()
        seen.append(tenancy.current_version(db, school.id))
    assert seen == sorted(seen) and len(set(seen)) == len(seen)


def test_invalidation_emits_one_tenant_scoped_event(db: Session) -> None:
    """§11: "svaki tenant događaj ima `tenant_id=school_id`; platform događaj
    koristi eksplicitni platform scope, ne `null` po navici". This one has
    exactly one school by definition, so there is nothing to fan out."""
    school = _provisioned(db)
    tenancy.invalidate(
        db,
        school.id,
        reason_code=TenantInvalidationReason.SUPPORT_ACCESS_REVOKED,
        correlation_id="corr-inv",
    )
    db.commit()

    messages = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.event_type == SCHOOL_ACCESS_INVALIDATED_EVENT
        )
    ).scalars().all()
    assert len(messages) == 1
    payload = messages[0].payload
    assert messages[0].school_id == school.id
    assert payload["tenant_access_version"] == tenancy.current_version(db, school.id)
    assert payload["dedupe_key"] == f"{school.id}:{payload['tenant_access_version']}"
    assert set(payload) == {
        "school_id",
        "tenant_access_version",
        "reason_code",
        "correlation_id",
        "dedupe_key",
    }


def test_the_event_is_not_the_guard(db: Session) -> None:
    """§14 and TEN-04: the next request is refused by an authoritative read, not
    by anything the outbox did. Proven by deleting the event and seeing the
    version stand."""
    school = _provisioned(db)
    tenancy.invalidate(
        db, school.id, reason_code=TenantInvalidationReason.LEGAL_HOLD
    )
    db.commit()
    bumped = tenancy.current_version(db, school.id)

    for message in db.execute(select(OutboxMessage)).scalars().all():
        db.delete(message)
    db.commit()
    assert tenancy.current_version(db, school.id) == bumped


def test_one_school_does_not_invalidate_another(db: Session) -> None:
    """§1: no response, cache, job or event may mix schools. The most basic
    form of that is that one tenant's security event stays in one tenant."""
    first = _provisioned(db, name="Prva")
    second = _provisioned(db, name="Druga")
    untouched = tenancy.current_version(db, second.id)

    tenancy.invalidate(
        db, first.id, reason_code=TenantInvalidationReason.SECURITY_INCIDENT
    )
    db.commit()
    assert tenancy.current_version(db, second.id) == untouched


def test_invalidating_an_unknown_school_is_refused(db: Session) -> None:
    with pytest.raises(NotFoundError):
        tenancy.invalidate(
            db, "sch_nepostojeca", reason_code=TenantInvalidationReason.PLATFORM_POLICY
        )


# ---------------------------------------------------------------------------
# §5.2 / §14 — atomic with the M04 status change
# ---------------------------------------------------------------------------


def test_deactivating_a_school_bumps_its_access_version(db: Session) -> None:
    """§5.2: "u istoj poslovnoj transakciji sa deaktiviranjem/reaktiviranjem"."""
    school = _provisioned(db)
    activated_at_version = tenancy.current_version(db, school.id)

    anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.DEACTIVATED,
        reason_code=SchoolStatusReason.OPERATIONAL_PAUSE,
        actor_ref="test",
        correlation_id="corr-deactivate",
    )
    db.commit()

    assert tenancy.current_version(db, school.id) > activated_at_version
    state = db.get(TenantSecurityState, school.id)
    assert state.last_invalidation_reason_code is (
        TenantInvalidationReason.SCHOOL_DEACTIVATED
    )


def test_reactivation_is_a_boundary_too(db: Session) -> None:
    """Coming back is as much a security event as going away: contexts built
    while the school was deactivated were built under different rules and must
    not simply resume."""
    school = _provisioned(db)
    anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.DEACTIVATED,
        reason_code=SchoolStatusReason.OPERATIONAL_PAUSE,
        actor_ref="test",
        correlation_id="corr",
    )
    db.commit()
    while_down = tenancy.current_version(db, school.id)

    anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.ACTIVE,
        reason_code=SchoolStatusReason.OPERATIONAL_RESUME,
        actor_ref="test",
        correlation_id="corr-reactivate",
    )
    db.commit()

    assert tenancy.current_version(db, school.id) > while_down
    state = db.get(TenantSecurityState, school.id)
    assert state.last_invalidation_reason_code is (
        TenantInvalidationReason.SCHOOL_REACTIVATED
    )


def test_a_refused_transition_leaves_the_version_alone(db: Session) -> None:
    """The bump rides the transition. A transition that never happened must not
    leave a security event behind suggesting it did."""
    school = _provisioned(db)
    before = tenancy.current_version(db, school.id)
    with pytest.raises(ConflictError):
        # ACTIVE -> ACTIVE: refused, and must leave nothing behind.
        anchor.transition_status(
            db,
            school=school,
            to_status=SchoolStatus.ACTIVE,
            reason_code=SchoolStatusReason.INITIAL_ACTIVATION,
            actor_ref="test",
            correlation_id="corr-bad",
        )
    db.rollback()
    assert tenancy.current_version(db, school.id) == before


# ---------------------------------------------------------------------------
# F-27 — the dead table is gone
# ---------------------------------------------------------------------------


def test_the_workspace_table_is_gone() -> None:
    """It was a reserved placeholder with no writer, no reader and no inbound
    foreign key, and M04's `organization` / `school_product_entitlement` took
    the role it was holding. Its name also collided with M03 §3's
    `workspace_key`, which is a display focus with no table at all.

    Asserted against the declared metadata rather than against
    `to_regclass('public.workspace')`: a live database keeps whatever it was
    given, so that query passes or fails on the *history* of the database the
    test happens to run against. The migration's own drop is proven by running
    it, which is a different check in a different place.
    """
    from app.models_registry import Base

    assert "workspace" not in Base.metadata.tables


def test_every_school_has_exactly_one_security_state(db: Session) -> None:
    """The invariant the backfill established, checked as a property rather than
    on one row."""
    for name in ("Alfa", "Beta", "Gama"):
        _provisioned(db, name=name)
    schools = db.execute(select(func.count()).select_from(School)).scalar_one()
    states = db.execute(
        select(func.count()).select_from(TenantSecurityState)
    ).scalar_one()
    assert schools == states
