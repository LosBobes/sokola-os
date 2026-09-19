"""M07 §7.1: `GRD-05`, `GRD-06` — which guardian the school calls first.

Split from `guardian_commands` along a real seam. Whether an adult *is* a
child's guardian and which of several guardians is called first are different
questions with different lifecycles, and §3.8 keeps them apart in the only way
that matters: primacy "ne daje dodatne child permissions". Nothing here grants
anything.

The §7 contract is the same as the rest of the group — stable `request_id`,
`expected_version`, one transaction, no commit inside.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import (
    InvalidRelationshipTransitionError,
    NotFoundError,
    RelationshipExistsError,
    ValidationFailedError,
)
from app.domains.family.commands_support import check_version, record
from app.domains.family.enums import (
    PRIMARY_GUARDIAN_CHANGED_EVENT,
    DesignationStatus,
    LinkStatus,
)
from app.domains.family.guardian_commands import require_link
from app.domains.family.models import PrimaryGuardianContactDesignation
from app.platform import clock
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue


def designate_primary_guardian_contact(
    db: Session,
    *,
    school_id: str,
    child_person_id: str,
    guardian_child_link_id: str,
    actor_account_id: str,
    request_id: str,
    expected_current_designation_id: str | None = None,
    actor_person_id: str | None = None,
    correlation_id: str | None = None,
) -> PrimaryGuardianContactDesignation:
    """`GRD-05`. §5.4: the old row and the new one change together.

    `expected_current_designation_id` is §5.4's "expected current": the caller
    states which primacy they believe they are replacing, and `None` means they
    believe there is none. Two staff members replacing different primaries at
    once would otherwise both succeed at "replace whatever is there", and the
    second would silently undo the first.
    """
    guard = idempotency.begin(
        db,
        school_id,
        "m07.primary_guardian.designate",
        request_id,
        {
            "child_person_id": child_person_id,
            "guardian_child_link_id": guardian_child_link_id,
            "expected_current_designation_id": expected_current_designation_id,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return _require_designation(db, school_id, guard.replay["body"]["id"])

    link = require_link(db, school_id, guardian_child_link_id, for_update=True)
    # §2.6: the link must be ACTIVE and for this child. The composite foreign
    # key already makes the second impossible; the first changes over time and
    # so has to be read here.
    if link.status is not LinkStatus.ACTIVE:
        raise InvalidRelationshipTransitionError(
            "Primarni kontakt mora upućivati na aktivnu vezu."
        )
    if link.child_person_id != child_person_id:
        raise NotFoundError("Veza nije pronađena.")

    current = db.execute(
        select(PrimaryGuardianContactDesignation)
        .where(
            PrimaryGuardianContactDesignation.school_id == school_id,
            PrimaryGuardianContactDesignation.child_person_id == child_person_id,
            PrimaryGuardianContactDesignation.status == DesignationStatus.ACTIVE,
        )
        .with_for_update()
    ).scalar_one_or_none()
    current_id = current.id if current is not None else None
    if current_id != expected_current_designation_id:
        # §6 `M07_PRIMARY_CONFLICT`: somebody else moved it first.
        raise RelationshipExistsError(
            "Primarni kontakt je u međuvremenu promenjen."
        )

    moment = clock.now()
    if current is not None:
        current.status = DesignationStatus.SUPERSEDED
        current.ended_at = moment
        current.end_reason_code = "REPLACED"
        current.version += 1

    designation = PrimaryGuardianContactDesignation(
        school_id=school_id,
        child_person_id=child_person_id,
        guardian_child_link_id=guardian_child_link_id,
        status=DesignationStatus.ACTIVE,
        designated_by_account_id=actor_account_id,
        designated_at=moment,
        version=1,
    )
    db.add(designation)
    db.flush()

    record(
        db,
        school_id=school_id,
        action="m07.primary_guardian.designate",
        entity_type="primary_guardian_contact_designation",
        entity_id=designation.id,
        summary="Određen je primarni starateljski kontakt.",
        actor_person_id=actor_person_id,
    )
    enqueue(
        db,
        event_type=PRIMARY_GUARDIAN_CHANGED_EVENT,
        payload={
            "school_id": school_id,
            "child_person_id": child_person_id,
            "designation_id": designation.id,
            "guardian_child_link_id": guardian_child_link_id,
            "superseded_designation_id": current_id,
            "status": designation.status.value,
            "version": designation.version,
            "correlation_id": correlation_id,
            "dedupe_key": f"{designation.id}:{designation.version}",
        },
        school_id=school_id,
    )
    idempotency.complete(db, guard, status=201, body={"id": designation.id})
    return designation


def remove_primary_guardian_contact(
    db: Session,
    *,
    school_id: str,
    designation_id: str,
    expected_version: int,
    reason_code: str,
    actor_account_id: str,
    request_id: str,
    actor_person_id: str | None = None,
    correlation_id: str | None = None,
) -> PrimaryGuardianContactDesignation:
    """`GRD-06`. §5.4: to REVOKED, reason required.

    Leaves the child with no primary contact, which §3.1 explicitly allows:
    "primarni kontakt može privremeno biti nula, nikad stale".
    """
    if not reason_code.strip():
        raise ValidationFailedError("Razlog uklanjanja je obavezan.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.primary_guardian.remove",
        request_id,
        {
            "designation_id": designation_id,
            "expected_version": expected_version,
            "reason_code": reason_code,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return _require_designation(db, school_id, designation_id)

    designation = _require_designation(db, school_id, designation_id)
    if designation.status is not DesignationStatus.ACTIVE:
        raise InvalidRelationshipTransitionError("Označavanje je već završeno.")
    check_version(designation.version, expected_version)

    designation.status = DesignationStatus.REVOKED
    designation.ended_at = clock.now()
    designation.end_reason_code = reason_code
    designation.version += 1
    db.flush()

    record(
        db,
        school_id=school_id,
        action="m07.primary_guardian.remove",
        entity_type="primary_guardian_contact_designation",
        entity_id=designation.id,
        summary="Primarni starateljski kontakt je uklonjen.",
        actor_person_id=actor_person_id,
        context={"reason_code": reason_code},
    )
    enqueue(
        db,
        event_type=PRIMARY_GUARDIAN_CHANGED_EVENT,
        payload={
            "school_id": school_id,
            "child_person_id": designation.child_person_id,
            "designation_id": designation.id,
            "guardian_child_link_id": designation.guardian_child_link_id,
            "superseded_designation_id": None,
            "status": designation.status.value,
            "version": designation.version,
            "reason_code": reason_code,
            "correlation_id": correlation_id,
            "dedupe_key": f"{designation.id}:{designation.version}",
        },
        school_id=school_id,
    )
    idempotency.complete(db, guard, status=200, body={"id": designation.id})
    return designation


def _require_designation(
    db: Session, school_id: str, designation_id: str
) -> PrimaryGuardianContactDesignation:
    row = db.execute(
        select(PrimaryGuardianContactDesignation).where(
            PrimaryGuardianContactDesignation.school_id == school_id,
            PrimaryGuardianContactDesignation.id == designation_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Označavanje nije pronađeno.")
    return row


__all__ = [
    "designate_primary_guardian_contact",
    "remove_primary_guardian_contact",
]
