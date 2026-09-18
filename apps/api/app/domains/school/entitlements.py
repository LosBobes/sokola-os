"""Entitlement grant, replacement, revoke — and the read-time effectiveness rule.

The rule that matters most here is the smallest one. §3.8.2–3.8.3 define
*effective* as all of:

* ``status = ACTIVE``;
* ``valid_from <= now``;
* ``valid_until IS NULL OR now < valid_until`` — note strictly ``<``, so
  ``now == valid_until`` is already ineffective;
* the source organization is still the school's current one;
* the school is not ``DEACTIVATED``.

and §3.8.3 adds the part that is easy to get wrong: **read time is the
authority**, even when the expiry job has not yet stamped the row ``EXPIRED``.
A reader that trusts ``status`` alone hands a school a capability it stopped
paying for at midnight, and the row will still say ACTIVE tomorrow morning.

So :func:`is_effective` never consults ``status`` alone, and
:func:`has_capability` is the only thing callers should use.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError
from app.domains.school import anchor
from app.domains.school.entitlement_enums import (
    REVOCATION_REASONS,
    CapabilityKey,
    EntitlementGrantReason,
    EntitlementRevokeReason,
    EntitlementStatus,
)
from app.domains.school.entitlement_models import SchoolProductEntitlement
from app.domains.school.enums import SchoolStatus
from app.domains.school.models import School
from app.platform import clock


def _lock_school(db: Session, school_id: str) -> None:
    db.execute(text("SELECT 1 FROM school WHERE id = :id FOR UPDATE"), {"id": school_id})


# ---------------------------------------------------------------------------
# Effectiveness (§3.8.2–3.8.3)
# ---------------------------------------------------------------------------


def is_effective(
    db: Session,
    entitlement: SchoolProductEntitlement,
    *,
    at: dt.datetime | None = None,
) -> bool:
    """Every clause of §3.8.2, evaluated now rather than trusted from a column."""
    now = at or clock.now()

    if entitlement.status is not EntitlementStatus.ACTIVE:
        return False
    if entitlement.valid_from > now:
        return False
    # Strictly less than: `now == valid_until` is ineffective (§3.8.3).
    if entitlement.valid_until is not None and now >= entitlement.valid_until:
        return False

    school = db.get(School, entitlement.school_id)
    if school is None or school.status is SchoolStatus.DEACTIVATED:
        # §3.8.2, and §3.6.5: entitlement rows survive deactivation as history,
        # but nothing they name is executable while the school is off.
        return False

    # The organization that sold this must still be the one holding the school.
    # §3.1.6 requires a transfer to re-grant explicitly rather than carry
    # capabilities across, so a stale source reads as ineffective.
    link = anchor.current_organization_link(db, entitlement.school_id)
    return link is not None and link.organization_id == entitlement.source_organization_id


def effective_entitlement(
    db: Session, school_id: str, capability: CapabilityKey, *, at: dt.datetime | None = None
) -> SchoolProductEntitlement | None:
    candidate = db.execute(
        select(SchoolProductEntitlement).where(
            SchoolProductEntitlement.school_id == school_id,
            SchoolProductEntitlement.capability_key == capability,
            SchoolProductEntitlement.status == EntitlementStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if candidate is None or not is_effective(db, candidate, at=at):
        return None
    return candidate


def has_capability(
    db: Session, school_id: str, capability: CapabilityKey, *, at: dt.datetime | None = None
) -> bool:
    """The only question a caller should ask. Fail-closed by construction: an
    absent row, a stale organization and a deactivated school all read False."""
    return effective_entitlement(db, school_id, capability, at=at) is not None


def require_capability(
    db: Session, school_id: str, capability: CapabilityKey, *, at: dt.datetime | None = None
) -> None:
    """Guard for a command boundary.

    Deliberately its own error, distinct from a permission failure: §6's
    ``ENTITLEMENT_NOT_EFFECTIVE`` says nothing about whether the actor would
    have been allowed, because those are different problems with different
    fixes, and conflating them sends an owner to the wrong support queue.
    """
    if not has_capability(db, school_id, capability, at=at):
        raise ConflictError(
            "Ova mogućnost nije komercijalno dostupna za ovu školu.",
            details={"capability": capability.value},
        )


# ---------------------------------------------------------------------------
# ENT-01: grant / replace
# ---------------------------------------------------------------------------


def grant_entitlement(
    db: Session,
    *,
    school_id: str,
    capability: CapabilityKey,
    commercial_reference: str,
    reason: EntitlementGrantReason,
    actor_ref: str,
    valid_until: dt.datetime | None = None,
) -> SchoolProductEntitlement:
    """Grant a capability, atomically superseding any active grant for it.

    §3.8.4: the previous grant is *terminalized*, not edited. Rewriting it in
    place would erase which commercial reference was in force when — the one
    question an entitlement history exists to answer.
    """
    _lock_school(db, school_id)

    school = db.get(School, school_id)
    if school is None:
        raise NotFoundError("Škola nije pronađena.")

    link = anchor.current_organization_link(db, school_id)
    if link is None:
        raise ConflictError("Škola nema aktuelnu vezu sa organizacijom.")

    now = clock.now()
    if valid_until is not None and valid_until <= now:
        raise ConflictError("Rok važenja mora biti u budućnosti.")

    previous = db.execute(
        select(SchoolProductEntitlement).where(
            SchoolProductEntitlement.school_id == school_id,
            SchoolProductEntitlement.capability_key == capability,
            SchoolProductEntitlement.status == EntitlementStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if previous is not None:
        previous.status = EntitlementStatus.REVOKED
        previous.revoked_at = now
        previous.revocation_reason_code = EntitlementRevokeReason.REPLACED
        previous.version += 1
        # Flush before inserting: the partial unique index must never see two
        # ACTIVE rows for this (school, capability), not even mid-statement.
        db.flush()

    granted = SchoolProductEntitlement(
        school_id=school_id,
        source_organization_id=link.organization_id,
        capability_key=capability,
        status=EntitlementStatus.ACTIVE,
        valid_from=now,
        valid_until=valid_until,
        commercial_reference=commercial_reference,
        granted_by_actor_ref=actor_ref,
        granted_at=now,
        grant_reason_code=reason,
    )
    db.add(granted)
    db.flush()
    return granted


# ---------------------------------------------------------------------------
# ENT-02: revoke
# ---------------------------------------------------------------------------


def revoke_entitlement(
    db: Session,
    *,
    entitlement: SchoolProductEntitlement,
    reason: EntitlementRevokeReason,
    expected_version: int | None = None,
) -> SchoolProductEntitlement:
    if reason not in REVOCATION_REASONS:
        # REPLACED and ENTITLEMENT_EXPIRED are system codes. A revoke claiming
        # to be a replacement, with no replacement, is a lie the audit trail
        # would carry forever.
        raise ConflictError("Razlog opoziva nije iz dozvoljenog registra.")
    if entitlement.status is not EntitlementStatus.ACTIVE:
        raise ConflictError("Entitlement je već zatvoren.")
    if expected_version is not None and expected_version != entitlement.version:
        raise ConflictError("Entitlement je u međuvremenu izmenjen.")

    entitlement.status = EntitlementStatus.REVOKED
    entitlement.revoked_at = clock.now()
    entitlement.revocation_reason_code = reason
    entitlement.version += 1
    db.flush()
    return entitlement


# ---------------------------------------------------------------------------
# Expiry materialization
# ---------------------------------------------------------------------------


def materialize_expired(db: Session, *, at: dt.datetime | None = None) -> list[str]:
    """Stamp grants whose window has closed, and return their ids.

    Bookkeeping, not enforcement. Everything this marks was *already*
    ineffective by :func:`is_effective`; the job exists so reporting and the
    admin surface agree with the reader, not so the reader can wait for it.
    """
    now = at or clock.now()
    due = (
        db.execute(
            select(SchoolProductEntitlement).where(
                SchoolProductEntitlement.status == EntitlementStatus.ACTIVE,
                SchoolProductEntitlement.valid_until.is_not(None),
                SchoolProductEntitlement.valid_until <= now,
            )
        )
        .scalars()
        .all()
    )
    for row in due:
        row.status = EntitlementStatus.EXPIRED
        row.expired_at = now
        row.version += 1
    db.flush()
    return [row.id for row in due]


def entitlement_history(
    db: Session, school_id: str, capability: CapabilityKey | None = None
) -> list[SchoolProductEntitlement]:
    stmt = select(SchoolProductEntitlement).where(
        SchoolProductEntitlement.school_id == school_id
    )
    if capability is not None:
        stmt = stmt.where(SchoolProductEntitlement.capability_key == capability)
    return list(db.execute(stmt.order_by(SchoolProductEntitlement.granted_at)).scalars().all())
