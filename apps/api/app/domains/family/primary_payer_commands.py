"""M07 §7.1: `PAY-05`, `PAY-06` — which payer the school bills by default.

§3.9 draws the line this module must not cross: the primary payer is the
default billing contact and "ne određuje procenat odgovornosti". It picks who
gets the invoice first. M12 may split an obligation across several ACTIVE payer
links, and nothing here says how — a field for a percentage would be this
module quietly answering a question that belongs to finance.

Mirrors `primary_contact_commands` exactly, because §2.7 says the fields are
the same as §2.6's. The two are separate tables and separate commands for the
reason §2.6 and §2.7 are separate entities: a child may have one active
primary contact **and** one active primary payer, independently.
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
    PRIMARY_PAYER_CHANGED_EVENT,
    DesignationStatus,
    LinkStatus,
)
from app.domains.family.models import PrimaryPayerDesignation
from app.domains.family.payer_commands import require_payer_link
from app.platform import clock
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue

_ENTITY = "primary_payer_designation"


def designate_primary_payer(
    db: Session,
    *,
    school_id: str,
    child_person_id: str,
    payer_child_link_id: str,
    actor_account_id: str,
    request_id: str,
    expected_current_designation_id: str | None = None,
    actor_person_id: str | None = None,
    correlation_id: str | None = None,
) -> PrimaryPayerDesignation:
    """`PAY-05`. §5.4: the old row and the new one change together.

    `expected_current_designation_id` is §5.4's "expected current", and `None`
    means the caller believes there is none. Without it, two staff members
    setting different primary payers at once would both succeed at "replace
    whatever is there" and the second would silently undo the first — which,
    for a billing default, means invoices going to the wrong adult with nothing
    in the record explaining why.
    """
    guard = idempotency.begin(
        db,
        school_id,
        "m07.primary_payer.designate",
        request_id,
        {
            "child_person_id": child_person_id,
            "payer_child_link_id": payer_child_link_id,
            "expected_current_designation_id": expected_current_designation_id,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return _require_designation(db, school_id, guard.replay["body"]["id"])

    link = require_payer_link(db, school_id, payer_child_link_id, for_update=True)
    # §2.7: the link must be ACTIVE and for this child. The composite foreign
    # key already makes the second impossible; status changes over time and so
    # has to be read here.
    if link.status is not LinkStatus.ACTIVE:
        raise InvalidRelationshipTransitionError(
            "Primarni platilac mora upućivati na aktivnu vezu."
        )
    if link.child_person_id != child_person_id:
        raise NotFoundError("Veza nije pronađena.")

    current = db.execute(
        select(PrimaryPayerDesignation)
        .where(
            PrimaryPayerDesignation.school_id == school_id,
            PrimaryPayerDesignation.child_person_id == child_person_id,
            PrimaryPayerDesignation.status == DesignationStatus.ACTIVE,
        )
        .with_for_update()
    ).scalar_one_or_none()
    current_id = current.id if current is not None else None
    if current_id != expected_current_designation_id:
        raise RelationshipExistsError("Primarni platilac je u međuvremenu promenjen.")

    moment = clock.now()
    if current is not None:
        current.status = DesignationStatus.SUPERSEDED
        current.ended_at = moment
        current.end_reason_code = "REPLACED"
        current.version += 1

    designation = PrimaryPayerDesignation(
        school_id=school_id,
        child_person_id=child_person_id,
        payer_child_link_id=payer_child_link_id,
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
        entity_type=_ENTITY,
        action="m07.primary_payer.designate",
        entity_id=designation.id,
        summary="Određen je primarni platilac.",
        actor_person_id=actor_person_id,
    )
    _emit(
        db,
        school_id=school_id,
        designation=designation,
        superseded_id=current_id,
        correlation_id=correlation_id,
    )
    idempotency.complete(db, guard, status=201, body={"id": designation.id})
    return designation


def remove_primary_payer(
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
) -> PrimaryPayerDesignation:
    """`PAY-06`. §5.4: to REVOKED, reason required.

    Leaves the child with no primary payer while other ACTIVE payer links may
    still exist — §2.7 allows exactly that. "Nobody is the default" and "nobody
    pays" are different states, and only the first one this command produces.
    """
    if not reason_code.strip():
        raise ValidationFailedError("Razlog uklanjanja je obavezan.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.primary_payer.remove",
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
        entity_type=_ENTITY,
        action="m07.primary_payer.remove",
        entity_id=designation.id,
        summary="Primarni platilac je uklonjen.",
        actor_person_id=actor_person_id,
        context={"reason_code": reason_code},
    )
    _emit(
        db,
        school_id=school_id,
        designation=designation,
        superseded_id=None,
        correlation_id=correlation_id,
        reason_code=reason_code,
    )
    idempotency.complete(db, guard, status=200, body={"id": designation.id})
    return designation


def _require_designation(
    db: Session, school_id: str, designation_id: str
) -> PrimaryPayerDesignation:
    row = db.execute(
        select(PrimaryPayerDesignation).where(
            PrimaryPayerDesignation.school_id == school_id,
            PrimaryPayerDesignation.id == designation_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Označavanje nije pronađeno.")
    return row


def _emit(
    db: Session,
    *,
    school_id: str,
    designation: PrimaryPayerDesignation,
    superseded_id: str | None,
    correlation_id: str | None,
    reason_code: str | None = None,
) -> None:
    enqueue(
        db,
        event_type=PRIMARY_PAYER_CHANGED_EVENT,
        payload={
            "school_id": school_id,
            "child_person_id": designation.child_person_id,
            "designation_id": designation.id,
            "payer_child_link_id": designation.payer_child_link_id,
            "superseded_designation_id": superseded_id,
            "status": designation.status.value,
            "version": designation.version,
            "reason_code": reason_code,
            "correlation_id": correlation_id,
            "dedupe_key": f"{designation.id}:{designation.version}",
        },
        school_id=school_id,
    )


__all__ = ["designate_primary_payer", "remove_primary_payer"]
