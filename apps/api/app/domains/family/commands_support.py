"""Helpers shared by M07's three command groups.

These lived in `guardian_commands` while it was the only group that needed
them, and `primary_contact_commands` imported them from there. That was fine
for two modules and stops being fine at four: the payer group has no business
importing from the guardian group to find out how to write an audit entry, and
a module that others import for utilities but not for its own subject is a
module in the wrong shape.

Nothing here decides anything about families, guardians or payers. It is the
three mechanics every M07 command repeats.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import ForbiddenError, StaleVersionError
from app.domains.identity.auth_models import UserAccount
from app.platform.audit.service import record_audit


def check_version(actual: int, expected: int) -> None:
    """§7's `expected_version` guard."""
    if actual != expected:
        raise StaleVersionError("Podaci su u međuvremenu izmenjeni.")


def person_for_account(db: Session, account_id: str) -> str | None:
    """Which person an M01 account belongs to, or `None` if it is not one.

    `None` rather than an error: an `actor_account_id` that names no account is
    a caller problem the permission layer catches, and treating it as "no
    person" here keeps :func:`refuse_self_decision` from turning a missing
    account into a silent pass.
    """
    return db.execute(
        select(UserAccount.person_id).where(UserAccount.id == account_id)
    ).scalar_one_or_none()


def refuse_self_decision(
    db: Session,
    *,
    requested_by_account_id: str,
    decider_account_id: str,
    party_person_ids: tuple[str, ...],
) -> None:
    """§5.3's distinct approver and §3.6's `M07_SELF_VERIFICATION_FORBIDDEN`.

    Two checks that read as one rule. The deciding account must differ from the
    requesting one — otherwise "two people looked at this" is one person twice
    — **and** it must not belong to anyone the link is about, or a guardian
    approves their own guardianship through a second account they happen to
    hold.

    The second check is why this cannot be a database constraint: it needs M01
    to say which person an account belongs to, and a CHECK sees two unequal ids
    and is satisfied.
    """
    if decider_account_id == requested_by_account_id:
        raise ForbiddenError("Odluku ne može doneti nalog koji je podneo zahtev.")
    decider_person_id = person_for_account(db, decider_account_id)
    if decider_person_id is not None and decider_person_id in party_person_ids:
        raise ForbiddenError("Nalog ne može odlučivati o sopstvenoj vezi.")


def record(
    db: Session,
    *,
    school_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    actor_person_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """One audit entry in the caller's transaction, under M07's data class.

    Shared so every M07 command classifies the same way. A relationship
    decision filed under a different class is one a later privacy review will
    not find.
    """
    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        school_id=school_id,
        actor_person_id=actor_person_id,
        context=context,
    )


__all__ = [
    "check_version",
    "person_for_account",
    "record",
    "refuse_self_decision",
]
