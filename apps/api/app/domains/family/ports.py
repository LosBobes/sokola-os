"""M07 §7.2: the read ports other modules resolve a subject basis through.

Four questions, deliberately narrow. Every answer is opaque ids and version
numbers — §4 requires it ("bez PII") — so a caller learns whether a basis
exists and nothing about the people it concerns. A module that needs a name
asks M06 with its own permission; it does not get one smuggled out of here.

**Why `ports` and not `service`.** The architecture gate stops one domain
importing another's `service`, `repository`, `router` or `policy`, and that
list is the point: these are meant to be imported. M12 cannot bill without
`eligible_payers_for_billing`, and M14 cannot address a message without
`primary_guardian_contact`. Naming the module for what it is makes the
intended coupling visible instead of dressing it as an accident — and keeps
the *decision-making* halves of M07 (the command groups) exactly as
unreachable as they were.

Nothing here reads the old `guardian_relationship` / `guardian_school_access`
tables. Those still have all 107 of their readers (F-31); these ports are what
the migration off them will move readers *to*, one domain at a time.

The sharpest rule is §3.7's, and it shows up as a return type.
:func:`payer_subject_basis` answers `FINANCE_ONLY` and carries no guardian
implication whatsoever: M05 §3.2 point 9 says a `PAYER` basis "nikad ne daje
attendance/document/health/profile/guardian pravo", so a payer basis and a
guardian basis are different dataclasses rather than one with a flag. A caller
cannot reach for the wrong field, because the field is not there.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.family.enums import DesignationStatus, LinkStatus
from app.domains.family.models import (
    GuardianChildLink,
    PayerChildLink,
    PrimaryGuardianContactDesignation,
)
from app.domains.school.enums import MembershipStatus
from app.domains.school.models import SchoolMembership

#: §7.2: what a payer basis authorizes, stated in the answer itself rather than
#: left for the caller to remember.
FINANCE_ONLY = "FINANCE_ONLY"


@dataclass(frozen=True, slots=True)
class GuardianBasis:
    """§7.2: an active guardian link, as much of it as a caller may know.

    The membership versions are here so a caller doing a high-risk write can
    re-check immediately before commit (§3.11) without another round trip, and
    so a stale basis is detectable rather than merely unlikely.
    """

    link_id: str
    link_version: int
    guardian_membership_version: int
    child_membership_version: int


@dataclass(frozen=True, slots=True)
class PayerBasis:
    """§7.2, §3.7: an active payer link, and what it does *not* carry.

    A separate type from :class:`GuardianBasis` on purpose. The two are not a
    single record with a flag, because a flag is something a caller can forget
    to read — and forgetting it here means handing a payer the child's
    attendance, documents and profile, which is the exact failure §2.5 exists
    to make impossible.
    """

    link_id: str
    link_version: int
    payer_membership_version: int
    child_membership_version: int
    #: Always `FINANCE_ONLY`. Present so the constraint travels with the answer.
    scope: str = FINANCE_ONLY


def _active_membership_version(db: Session, membership_id: str) -> int | None:
    """The membership's version, but only while it is `ACTIVE`.

    The status check is the load-bearing half. §12 says "Završetak M06
    membership-a čini link neefektivnim odmah" and that the request-time
    resolver "ne čeka consumer" — so a terminated membership has to stop
    answering here, not once some consumer gets round to closing the link.

    `SUSPENDED` and `DRAFT` are refused too, which is a wider reading than §12
    strictly requires and the deliberate one: M03 §6.1 already treats current
    ACTIVE membership as the evidence any regular access needs, and a port that
    answered "basis exists" for a suspended member would be handing that
    decision to whichever caller happened to look — differently in each one.

    Note what this check is *not* for: the row going missing. Both link tables
    hold their memberships with `ON DELETE RESTRICT`, so a membership a link
    names cannot be deleted at all. The `None` below is the status case.
    """
    return db.execute(
        select(SchoolMembership.version).where(
            SchoolMembership.id == membership_id,
            SchoolMembership.status == MembershipStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def guardian_subject_basis(
    db: Session, *, school_id: str, guardian_person_id: str, child_person_id: str
) -> GuardianBasis | None:
    """§7.2 `GuardianSubjectBasisPort.resolve`. `None` is §6's safe not-found.

    `None` rather than an exception because this answers a question. A caller
    that needs `M07_NOT_FOUND_SAFE` raises it at the edge, where it also knows
    whether the caller was even allowed to ask — and §4 requires unknown,
    cross-tenant and not-permitted to look identical, which only the edge can
    guarantee.
    """
    link = db.execute(
        select(GuardianChildLink).where(
            GuardianChildLink.school_id == school_id,
            GuardianChildLink.guardian_person_id == guardian_person_id,
            GuardianChildLink.child_person_id == child_person_id,
            GuardianChildLink.status == LinkStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if link is None:
        return None

    guardian_version = _active_membership_version(db, link.guardian_school_membership_id)
    child_version = _active_membership_version(db, link.child_school_membership_id)
    if guardian_version is None or child_version is None:
        # §12: a membership that has ended makes the link ineffective *now*.
        # Fail closed — the alternative is a request going through on a link
        # whose foundation the school has already withdrawn.
        return None

    return GuardianBasis(
        link_id=link.id,
        link_version=link.version,
        guardian_membership_version=guardian_version,
        child_membership_version=child_version,
    )


def payer_subject_basis(
    db: Session, *, school_id: str, payer_person_id: str, child_person_id: str
) -> PayerBasis | None:
    """§7.2 `PayerSubjectBasisPort.resolve` — finance and nothing else.

    Returns no `basis_kind`. Why this adult pays is M07's own record; a billing
    module needs to know *that* an active link exists, and "because they are
    family" is a statement about the relationship that §4 keeps out of what
    leaves the module.
    """
    link = db.execute(
        select(PayerChildLink).where(
            PayerChildLink.school_id == school_id,
            PayerChildLink.payer_person_id == payer_person_id,
            PayerChildLink.child_person_id == child_person_id,
            PayerChildLink.status == LinkStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if link is None:
        return None

    payer_version = _active_membership_version(db, link.payer_school_membership_id)
    child_version = _active_membership_version(db, link.child_school_membership_id)
    if payer_version is None or child_version is None:
        return None

    return PayerBasis(
        link_id=link.id,
        link_version=link.version,
        payer_membership_version=payer_version,
        child_membership_version=child_version,
    )


def primary_guardian_contact(
    db: Session, *, school_id: str, child_person_id: str
) -> str | None:
    """§7.2 `PrimaryContactPort.get` → zero or one active guardian link id.

    Zero is a real answer, not an error. §3.1 says "primarni kontakt može
    privremeno biti nula, nikad stale" — the moment a link is revoked its
    designation closes with it, and a child legitimately has no primary contact
    until someone designates again. A caller that treats `None` as a failure
    has misread which of the two states is the dangerous one.
    """
    return db.execute(
        select(PrimaryGuardianContactDesignation.guardian_child_link_id).where(
            PrimaryGuardianContactDesignation.school_id == school_id,
            PrimaryGuardianContactDesignation.child_person_id == child_person_id,
            PrimaryGuardianContactDesignation.status == DesignationStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def eligible_payers_for_billing(
    db: Session, *, school_id: str, child_person_id: str
) -> tuple[str, ...]:
    """§7.2 `EligiblePayersPort.listForBilling` → active payer link ids.

    Ids only, and no ordering that implies precedence. §3.9 says the primary
    payer "ne određuje procenat odgovornosti" and §2.5 that M12 decides how an
    obligation is split, so returning these sorted by anything M07 knows —
    designation, creation order — would be M07 answering a question it was told
    not to. Sorted by id, which means nothing at all.
    """
    return tuple(
        db.execute(
            select(PayerChildLink.id)
            .where(
                PayerChildLink.school_id == school_id,
                PayerChildLink.child_person_id == child_person_id,
                PayerChildLink.status == LinkStatus.ACTIVE,
            )
            .order_by(PayerChildLink.id)
        )
        .scalars()
        .all()
    )


__all__ = [
    "FINANCE_ONLY",
    "GuardianBasis",
    "PayerBasis",
    "eligible_payers_for_billing",
    "guardian_subject_basis",
    "payer_subject_basis",
    "primary_guardian_contact",
]
