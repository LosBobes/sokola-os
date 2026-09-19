"""M04 §2.8, §3.8: what a school has been sold, and when that stops being true.

The tests that matter most are the ones about *read time*. An entitlement row
keeps saying ACTIVE after its window closes until some job gets round to
stamping it, so any reader that trusts `status` hands a school a capability it
stopped paying for at midnight — and the row will still look fine tomorrow.
§3.8.3 makes read time the authority, and that is what is driven here.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import ConflictError
from app.common.ids import new_id
from app.domains.organization.enums import (
    OrganizationSchoolChangeReason,
    OrganizationStatus,
)
from app.domains.organization.models import Organization
from app.domains.school import anchor, entitlements
from app.domains.school.entitlement_enums import (
    CapabilityKey,
    EntitlementGrantReason,
    EntitlementRevokeReason,
    EntitlementStatus,
)
from app.domains.school.entitlement_models import SchoolProductEntitlement
from app.domains.school.enums import SchoolStatus, SchoolStatusReason
from app.platform import clock
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import make_school

CORE = CapabilityKey.CORE_MVP
MY = CapabilityKey.MYSOKOLA_BASIC


def _grant(db: Session, school, capability=CORE, **kwargs):
    return entitlements.grant_entitlement(
        db,
        school_id=school.id,
        capability=capability,
        commercial_reference=kwargs.pop("ref", "CONTRACT-1"),
        reason=kwargs.pop("reason", EntitlementGrantReason.CONTRACT_ACTIVATED),
        actor_ref="platform",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Absence is the default (§2.8)
# ---------------------------------------------------------------------------


def test_a_school_starts_with_nothing_granted(db: Session) -> None:
    """§2.8: CORE_MVP does not arise from an organization link. Being held by an
    organization is not the same as having been sold to."""
    school = make_school(db)
    assert anchor.current_organization_link(db, school.id) is not None

    for capability in CapabilityKey:
        assert not entitlements.has_capability(db, school.id, capability)


def test_require_capability_names_the_commercial_problem(db: Session) -> None:
    """§6: ENTITLEMENT_NOT_EFFECTIVE says nothing about permission. They are
    different problems, and conflating them sends an owner to the wrong queue."""
    school = make_school(db)
    with pytest.raises(ConflictError) as raised:
        entitlements.require_capability(db, school.id, CORE)
    assert raised.value.details["capability"] == "CORE_MVP"


# ---------------------------------------------------------------------------
# Read-time effectiveness (§3.8.2–3.8.3)
# ---------------------------------------------------------------------------


def test_a_granted_capability_is_effective(db: Session) -> None:
    school = make_school(db)
    granted = _grant(db, school)
    db.flush()

    assert entitlements.has_capability(db, school.id, CORE)
    assert entitlements.effective_entitlement(db, school.id, CORE) is granted
    # Granting one capability grants nothing else.
    assert not entitlements.has_capability(db, school.id, MY)


def test_the_instant_of_expiry_is_already_ineffective(db: Session) -> None:
    """§3.8.3: `now == valid_until` means not effective. An inclusive comparison
    here would give away a free interval whose length is however long the job
    takes to run."""
    school = make_school(db)
    with clock.frozen_at("2026-06-01T00:00:00+00:00"):
        granted = _grant(db, school, valid_until=dt.datetime(2026, 7, 1, tzinfo=dt.UTC))
        db.flush()
        assert entitlements.is_effective(db, granted)

    one_before = dt.datetime(2026, 6, 30, 23, 59, 59, 999999, tzinfo=dt.UTC)
    assert entitlements.is_effective(db, granted, at=one_before)
    assert not entitlements.is_effective(db, granted, at=dt.datetime(2026, 7, 1, tzinfo=dt.UTC))


def test_an_expired_window_is_ineffective_before_any_job_runs(db: Session) -> None:
    """The row still says ACTIVE. That is exactly the case §3.8.3 is about."""
    school = make_school(db)
    with clock.frozen_at("2026-06-01T00:00:00+00:00"):
        granted = _grant(db, school, valid_until=dt.datetime(2026, 7, 1, tzinfo=dt.UTC))
        db.flush()

    with clock.frozen_at("2026-08-01T00:00:00+00:00"):
        assert granted.status is EntitlementStatus.ACTIVE
        assert granted.expired_at is None
        assert not entitlements.has_capability(db, school.id, CORE)
        with pytest.raises(ConflictError):
            entitlements.require_capability(db, school.id, CORE)


def test_a_future_grant_is_not_yet_effective(db: Session) -> None:
    school = make_school(db)
    with clock.frozen_at("2026-06-01T00:00:00+00:00"):
        granted = _grant(db, school)
        db.flush()
    assert not entitlements.is_effective(
        db, granted, at=dt.datetime(2026, 5, 1, tzinfo=dt.UTC)
    )


def test_a_deactivated_school_executes_nothing(db: Session) -> None:
    """§3.6.5: the row survives deactivation as history, but nothing it names is
    executable while the school is off."""
    school = make_school(db)
    _grant(db, school)
    db.flush()
    assert entitlements.has_capability(db, school.id, CORE)

    anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.DEACTIVATED,
        reason_code=SchoolStatusReason.PILOT_PAUSED,
        reason_note="Pauza.",
        actor_ref="platform",
        correlation_id=new_id("corr"),
    )
    db.flush()

    assert not entitlements.has_capability(db, school.id, CORE)
    # But the history is intact.
    assert len(entitlements.entitlement_history(db, school.id)) == 1


def test_an_organization_transfer_does_not_carry_capabilities_across(db: Session) -> None:
    """§3.1.6: a transfer replaces the entitlement set with an explicitly
    approved one. Anything still pointing at the old organization is stale, and
    stale reads as ineffective rather than as "probably fine"."""
    school = make_school(db)
    _grant(db, school)
    db.flush()
    assert entitlements.has_capability(db, school.id, CORE)

    successor = Organization(
        organization_ref=new_id("oref"),
        legal_name="Novi holder d.o.o.",
        country_code="RS",
        status=OrganizationStatus.ACTIVE,
        created_by_actor_ref="platform",
        updated_by_actor_ref="platform",
    )
    db.add(successor)
    db.flush()
    anchor.transfer_organization(
        db,
        school_id=school.id,
        organization=successor,
        reason=OrganizationSchoolChangeReason.LEGAL_OWNERSHIP_TRANSFER,
        case_reference="CASE-9",
        actor_ref="platform",
    )
    db.flush()

    assert not entitlements.has_capability(db, school.id, CORE)

    # The new organization has to grant it explicitly, and then it works again.
    regranted = _grant(db, school, reason=EntitlementGrantReason.ORGANIZATION_TRANSFER)
    db.flush()
    assert regranted.source_organization_id == successor.id
    assert entitlements.has_capability(db, school.id, CORE)


# ---------------------------------------------------------------------------
# Grant and replacement (§3.8.4)
# ---------------------------------------------------------------------------


def test_a_new_grant_terminalizes_the_previous_one_rather_than_editing_it(
    db: Session,
) -> None:
    """History is what an entitlement table is for: which commercial reference
    was in force when. Rewriting the old row in place erases exactly that."""
    school = make_school(db)
    first = _grant(db, school, ref="PILOT-1", reason=EntitlementGrantReason.PILOT_APPROVED)
    db.flush()
    second = _grant(db, school, ref="CONTRACT-7", reason=EntitlementGrantReason.PLAN_CHANGED)
    db.flush()

    assert first.status is EntitlementStatus.REVOKED
    assert first.revocation_reason_code is EntitlementRevokeReason.REPLACED
    assert first.commercial_reference == "PILOT-1"  # untouched
    assert second.status is EntitlementStatus.ACTIVE
    assert second.commercial_reference == "CONTRACT-7"
    assert entitlements.effective_entitlement(db, school.id, CORE) is second
    assert len(entitlements.entitlement_history(db, school.id, CORE)) == 2


def test_the_database_refuses_two_active_grants_for_one_capability(db: Session) -> None:
    school = make_school(db)
    granted = _grant(db, school)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO school_product_entitlement (id, school_id, source_organization_id, "
                "capability_key, status, valid_from, commercial_reference, granted_by_actor_ref, "
                "granted_at, grant_reason_code, version, created_at, updated_at) "
                "VALUES (:id, :s, :o, 'CORE_MVP', 'ACTIVE', now(), 'X', 'x', now(), "
                "'CONTRACT_ACTIVATED', 1, now(), now())"
            ),
            {"id": new_id("ent"), "s": school.id, "o": granted.source_organization_id},
        )
    db.rollback()


def test_different_capabilities_are_independent(db: Session) -> None:
    school = make_school(db)
    _grant(db, school, capability=CORE)
    _grant(db, school, capability=MY)
    db.flush()

    assert entitlements.has_capability(db, school.id, CORE)
    assert entitlements.has_capability(db, school.id, MY)
    assert not entitlements.has_capability(db, school.id, CapabilityKey.OPERATIONS)


def test_a_grant_needs_a_current_organization(db: Session) -> None:
    school = make_school(db)
    link = anchor.current_organization_link(db, school.id)
    assert link is not None
    link.valid_to = clock.now()
    db.flush()

    with pytest.raises(ConflictError, match="organizacijom"):
        _grant(db, school)


def test_a_validity_window_must_end_in_the_future(db: Session) -> None:
    school = make_school(db)
    with (
        clock.frozen_at("2026-06-01T00:00:00+00:00"),
        pytest.raises(ConflictError, match="budućnosti"),
    ):
        _grant(db, school, valid_until=dt.datetime(2026, 5, 1, tzinfo=dt.UTC))


# ---------------------------------------------------------------------------
# Revoke (§8.1.2)
# ---------------------------------------------------------------------------


def test_revoking_takes_effect_immediately(db: Session) -> None:
    school = make_school(db)
    granted = _grant(db, school)
    db.flush()

    entitlements.revoke_entitlement(
        db,
        entitlement=granted,
        reason=EntitlementRevokeReason.CONTRACT_ENDED,
        expected_version=granted.version,
    )
    db.flush()

    assert granted.status is EntitlementStatus.REVOKED
    assert granted.revoked_at is not None
    assert not entitlements.has_capability(db, school.id, CORE)


@pytest.mark.parametrize(
    "reason",
    [EntitlementRevokeReason.REPLACED, EntitlementRevokeReason.ENTITLEMENT_EXPIRED],
)
def test_a_system_reason_cannot_be_claimed_by_a_caller(
    db: Session, reason: EntitlementRevokeReason
) -> None:
    """A revoke that says REPLACED, with no replacement, is a lie the audit
    trail would carry forever."""
    school = make_school(db)
    granted = _grant(db, school)
    db.flush()

    with pytest.raises(ConflictError, match="registra"):
        entitlements.revoke_entitlement(db, entitlement=granted, reason=reason)
    assert granted.status is EntitlementStatus.ACTIVE


def test_a_stale_version_does_not_revoke(db: Session) -> None:
    school = make_school(db)
    granted = _grant(db, school)
    db.flush()
    granted.version += 1  # someone else moved first

    with pytest.raises(ConflictError, match="izmenjen"):
        entitlements.revoke_entitlement(
            db,
            entitlement=granted,
            reason=EntitlementRevokeReason.CONTRACT_ENDED,
            expected_version=1,
        )


def test_revoking_twice_is_refused(db: Session) -> None:
    school = make_school(db)
    granted = _grant(db, school)
    db.flush()
    entitlements.revoke_entitlement(
        db, entitlement=granted, reason=EntitlementRevokeReason.PILOT_ENDED
    )
    db.flush()

    with pytest.raises(ConflictError, match="zatvoren"):
        entitlements.revoke_entitlement(
            db, entitlement=granted, reason=EntitlementRevokeReason.CONTRACT_ENDED
        )


def test_a_revoked_grant_frees_the_capability_for_a_new_one(db: Session) -> None:
    school = make_school(db)
    granted = _grant(db, school)
    db.flush()
    entitlements.revoke_entitlement(
        db, entitlement=granted, reason=EntitlementRevokeReason.CONTRACT_SUSPENDED
    )
    db.flush()

    fresh = _grant(db, school, ref="CONTRACT-NEW")
    db.flush()
    assert entitlements.effective_entitlement(db, school.id, CORE) is fresh
    assert len(entitlements.entitlement_history(db, school.id, CORE)) == 2


# ---------------------------------------------------------------------------
# Expiry materialization
# ---------------------------------------------------------------------------


def test_materializing_expiry_changes_bookkeeping_not_the_answer(db: Session) -> None:
    """Everything the job marks was already ineffective. It exists so reporting
    agrees with the reader, not so the reader has to wait for it."""
    school = make_school(db)
    with clock.frozen_at("2026-06-01T00:00:00+00:00"):
        granted = _grant(db, school, valid_until=dt.datetime(2026, 7, 1, tzinfo=dt.UTC))
        db.flush()

    with clock.frozen_at("2026-08-01T00:00:00+00:00"):
        before = entitlements.has_capability(db, school.id, CORE)
        marked = entitlements.materialize_expired(db)
        after = entitlements.has_capability(db, school.id, CORE)

    assert before is False and after is False
    assert marked == [granted.id]
    assert granted.status is EntitlementStatus.EXPIRED
    assert granted.expired_at == dt.datetime(2026, 8, 1, tzinfo=dt.UTC)


def test_materializing_leaves_open_ended_and_future_grants_alone(db: Session) -> None:
    school, other = make_school(db, name="Prva"), make_school(db, name="Druga")
    with clock.frozen_at("2026-06-01T00:00:00+00:00"):
        open_ended = _grant(db, school)
        still_valid = _grant(db, other, valid_until=dt.datetime(2027, 1, 1, tzinfo=dt.UTC))
        db.flush()
        assert entitlements.materialize_expired(db) == []

    assert open_ended.status is EntitlementStatus.ACTIVE
    assert still_valid.status is EntitlementStatus.ACTIVE


def test_the_database_refuses_an_expired_row_with_no_window(db: Session) -> None:
    """EXPIRED without a validity window is a contradiction on its face."""
    school = make_school(db)
    granted = _grant(db, school)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE school_product_entitlement SET status = 'EXPIRED', "
                "expired_at = now() WHERE id = :id"
            ),
            {"id": granted.id},
        )
    db.rollback()


def test_a_grant_survives_a_round_trip(db: Session) -> None:
    school = make_school(db)
    granted = _grant(db, school)
    db.commit()
    db.expire_all()

    stored = db.get(SchoolProductEntitlement, granted.id)
    assert stored is not None
    assert stored.capability_key is CORE
    assert stored.grant_reason_code is EntitlementGrantReason.CONTRACT_ACTIVATED
    assert stored.version == 1
    assert stored.valid_until is None
