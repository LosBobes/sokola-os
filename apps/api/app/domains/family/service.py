"""M07 §7.1: the FAM command group — creating and closing family groupings.

Four commands, `FAM-01` through `FAM-04`. Each follows §7's contract: a stable
`request_id` is the canonical idempotency key, an `expected_version` guards
every target that already exists, and the receipt, the domain rows, the audit
entry and the outbox event are **one transaction**. None of these functions
commits; the caller owns the transaction, which is the only way "jedna
transakcija" can actually hold.

**No router yet, deliberately.** §4 requires the chain M01 session → M03 school
context → M05 permission → M07 subject basis before any of this is reachable,
and M07's permission keys (`school.families.manage` and the rest of §4's list)
live in an M05 continuation registry that is still undetermined (F-30). Wiring
routes now would mean guarding them on the legacy `RoleCode` that F-29 is open
to replace — building the thing twice and leaving a half-guarded surface in
between. The commands are testable without it.

§3.13's archive rule is the interesting one. A family may be archived only when
nothing rests on it: no active membership, no open payer link, and no
outstanding M12 obligation. The first two this module can see. The third it
must not — an `app.domains.family` that imported M12 would be the
`M12 → M07 → M12` cycle the contract routes around — so `archive_family` takes
the check as a **required** port. There is no default, and that is the design:
a caller who has not consulted finance cannot archive a family by forgetting to.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import (
    DependencyUnavailableError,
    FamilyArchiveBlockedError,
    InvalidRelationshipTransitionError,
    NotFoundError,
    RelationshipExistsError,
    StaleVersionError,
    ValidationFailedError,
)
from app.domains.family.enums import (
    FAMILY_ARCHIVED_EVENT,
    FamilyMembershipStatus,
    FamilyStatus,
    LinkStatus,
    MemberKind,
)
from app.domains.family.models import (
    Family,
    FamilyMembership,
    PayerChildLink,
)
from app.domains.school.enums import MembershipStatus
from app.domains.school.models import SchoolMembership
from app.platform import clock
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue

#: Whether M12 still holds an obligation or credit against a family. Supplied
#: by the application layer; see the module docstring for why it has no
#: default. Raising from inside it is the honest way to report that finance
#: could not be reached — `archive_family` turns that into §6's 503 rather
#: than treating an unreachable guard as a clear "no".
FinancialBlockerPort = Callable[[str, str], bool]


def _require_open_family(db: Session, school_id: str, family_id: str) -> Family:
    family = db.execute(
        select(Family).where(Family.school_id == school_id, Family.id == family_id)
    ).scalar_one_or_none()
    if family is None:
        # §4: unknown, cross-tenant and not-allowed-to-know are one answer.
        raise NotFoundError("Porodica nije pronađena.")
    return family


def _check_version(actual: int, expected: int | None) -> None:
    if expected is not None and actual != expected:
        raise StaleVersionError("Podaci su u međuvremenu izmenjeni.")


def create_family(
    db: Session,
    *,
    school_id: str,
    actor_account_id: str,
    request_id: str,
    display_label: str | None = None,
    actor_person_id: str | None = None,
) -> Family:
    """`FAM-01 CreateFamily`. §5.1: from nothing to ACTIVE.

    Creates a grouping and nothing else. §3.1 is the rule that keeps this
    command as small as it looks: a family, a membership in it, a guardian
    link and a payer link are separate facts, so creating the first implies
    none of the others.
    """
    label = display_label.strip() if display_label else None
    if label is not None and not 1 <= len(label) <= 100:
        raise ValidationFailedError("Naziv porodice mora imati 1–100 znakova.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.family.create",
        request_id,
        {"display_label": label, "actor_account_id": actor_account_id},
    )
    if guard.replay is not None:
        return _require_open_family(db, school_id, guard.replay["body"]["id"])

    family = Family(
        school_id=school_id,
        display_label=label,
        status=FamilyStatus.ACTIVE,
        created_by_account_id=actor_account_id,
        version=1,
    )
    db.add(family)
    db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="m07.family.create",
        entity_type="family",
        entity_id=family.id,
        # §4: audit carries opaque IDs and codes, never names or free text
        # about a relationship. The label is the school's own words about a
        # household, so it stays out.
        summary="Porodična grupa je kreirana.",
        school_id=school_id,
        actor_person_id=actor_person_id,
    )
    idempotency.complete(db, guard, status=201, body={"id": family.id})
    return family


def archive_family(
    db: Session,
    *,
    school_id: str,
    family_id: str,
    expected_version: int,
    reason_code: str,
    actor_account_id: str,
    request_id: str,
    has_open_obligations: FinancialBlockerPort,
    actor_person_id: str | None = None,
    correlation_id: str | None = None,
) -> Family:
    """`FAM-02 ArchiveFamily`. §5.1, §3.13: "ARCHIVED ili potpuni fail".

    Three blockers, checked in cost order — the two this module can see from
    its own tables first, the cross-module one last, so a family that is
    obviously still in use never costs a call to finance.

    `has_open_obligations` is required and has no default. §3.13 routes the
    M12 question through application orchestration to avoid an
    `M12 → M07 → M12` cycle, and making the port a parameter is what turns
    that from a convention into something a caller cannot skip. If it raises,
    §6 says fail closed: 503, not "probably fine".
    """
    if not reason_code.strip():
        raise ValidationFailedError("Razlog arhiviranja je obavezan.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.family.archive",
        request_id,
        {
            "family_id": family_id,
            "expected_version": expected_version,
            "reason_code": reason_code,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return _require_open_family(db, school_id, family_id)

    family = _require_open_family(db, school_id, family_id)
    if family.status is not FamilyStatus.ACTIVE:
        # §5.1: ARCHIVED is terminal in H0; a family that re-forms is a new id.
        raise InvalidRelationshipTransitionError(
            "Porodična grupa je već arhivirana."
        )
    _check_version(family.version, expected_version)

    _refuse_if_anything_rests_on_it(
        db,
        school_id=school_id,
        family_id=family_id,
        has_open_obligations=has_open_obligations,
    )

    family.status = FamilyStatus.ARCHIVED
    family.archive_reason_code = reason_code
    family.version += 1
    db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="m07.family.archive",
        entity_type="family",
        entity_id=family.id,
        summary="Porodična grupa je arhivirana.",
        school_id=school_id,
        actor_person_id=actor_person_id,
        context={"reason_code": reason_code},
    )
    # §7.3: opaque IDs, status, version and a reason code. No names, no
    # contacts, no description of the relationship.
    enqueue(
        db,
        event_type=FAMILY_ARCHIVED_EVENT,
        payload={
            "school_id": school_id,
            "family_id": family.id,
            "status": family.status.value,
            "version": family.version,
            "reason_code": reason_code,
            "correlation_id": correlation_id,
            "dedupe_key": f"{family.id}:{family.version}",
        },
        school_id=school_id,
    )
    idempotency.complete(db, guard, status=200, body={"id": family.id})
    return family


def _refuse_if_anything_rests_on_it(
    db: Session,
    *,
    school_id: str,
    family_id: str,
    has_open_obligations: FinancialBlockerPort,
) -> None:
    """§3.13's three blockers, reported together rather than one at a time.

    An operator who clears the membership only to be told about a payer link,
    then clears that only to be told about an invoice, has been made to do
    three round trips for one answer. The refusal names every reason at once.
    """
    blockers: list[str] = []

    members = db.execute(
        select(func.count())
        .select_from(FamilyMembership)
        .where(
            FamilyMembership.school_id == school_id,
            FamilyMembership.family_id == family_id,
            FamilyMembership.status == FamilyMembershipStatus.ACTIVE,
        )
    ).scalar_one()
    if members:
        blockers.append(f"aktivnih članova: {members}")

    # Only a payer link names a family, so it is the only link that can rest
    # "isključivo" on one. A guardian link has no `family_id` at all — §2.3
    # ties it to memberships, not to a household.
    payers = db.execute(
        select(func.count())
        .select_from(PayerChildLink)
        .where(
            PayerChildLink.school_id == school_id,
            PayerChildLink.family_id == family_id,
            PayerChildLink.status.in_(
                (LinkStatus.PENDING_VERIFICATION, LinkStatus.ACTIVE)
            ),
        )
    ).scalar_one()
    if payers:
        blockers.append(f"otvorenih platilačkih veza: {payers}")

    try:
        financial = has_open_obligations(school_id, family_id)
    except Exception as exc:  # noqa: BLE001 - re-raised as §6's fail-closed 503
        raise DependencyUnavailableError(
            "Finansijska provera trenutno nije dostupna."
        ) from exc
    if financial:
        blockers.append("otvorenih finansijskih obaveza")

    if blockers:
        raise FamilyArchiveBlockedError(
            "Porodična grupa se ne može arhivirati: " + ", ".join(blockers) + "."
        )


def add_family_member(
    db: Session,
    *,
    school_id: str,
    family_id: str,
    person_id: str,
    member_kind: MemberKind,
    actor_account_id: str,
    request_id: str,
    effective_from: dt.date | None = None,
    actor_person_id: str | None = None,
) -> FamilyMembership:
    """`FAM-03 AddFamilyMember`. §5.2: Family ACTIVE, tenant-safe Person.

    The M06 membership has to be **open** at creation (§2.2). A terminated one
    would make the household record reference someone the school no longer
    has, and the composite foreign key would happily accept it — the key
    proves the membership belongs to this person and this tenant, not that it
    is current.
    """
    guard = idempotency.begin(
        db,
        school_id,
        "m07.family.add_member",
        request_id,
        {
            "family_id": family_id,
            "person_id": person_id,
            "member_kind": member_kind.value,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return _require_membership(db, school_id, guard.replay["body"]["id"])

    family = _require_open_family(db, school_id, family_id)
    if family.status is not FamilyStatus.ACTIVE:
        raise InvalidRelationshipTransitionError(
            "Članovi se ne dodaju u arhiviranu porodičnu grupu."
        )

    school_membership = db.execute(
        select(SchoolMembership).where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.person_id == person_id,
            SchoolMembership.status != MembershipStatus.TERMINATED,
        )
    ).scalars().first()
    if school_membership is None:
        raise NotFoundError("Osoba nema otvoreno članstvo u ovoj školi.")

    existing = db.execute(
        select(func.count())
        .select_from(FamilyMembership)
        .where(
            FamilyMembership.school_id == school_id,
            FamilyMembership.family_id == family_id,
            FamilyMembership.person_id == person_id,
            FamilyMembership.status == FamilyMembershipStatus.ACTIVE,
        )
    ).scalar_one()
    if existing:
        raise RelationshipExistsError("Osoba je već član ove porodične grupe.")

    membership = FamilyMembership(
        school_id=school_id,
        family_id=family_id,
        person_id=person_id,
        school_membership_id=school_membership.id,
        member_kind=member_kind,
        status=FamilyMembershipStatus.ACTIVE,
        effective_from=effective_from or clock.now().date(),
        version=1,
    )
    db.add(membership)
    db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="m07.family.add_member",
        entity_type="family_membership",
        entity_id=membership.id,
        summary="Osoba je dodata u porodičnu grupu.",
        school_id=school_id,
        actor_person_id=actor_person_id,
        context={"member_kind": member_kind.value},
    )
    idempotency.complete(db, guard, status=201, body={"id": membership.id})
    return membership


def end_family_membership(
    db: Session,
    *,
    school_id: str,
    membership_id: str,
    expected_version: int,
    reason_code: str,
    actor_account_id: str,
    request_id: str,
    effective_until: dt.date | None = None,
    actor_person_id: str | None = None,
) -> FamilyMembership:
    """`FAM-04 EndFamilyMembership`. §5.2: ENDED is terminal.

    No outbox event: §7.3's list has `FamilyArchived` and the link events, and
    not this one. A household composition change is the school's own record and
    nothing downstream acts on it — sending an event nobody consumes would be
    inventing a contract, and one carrying who lives with whom at that.
    """
    if not reason_code.strip():
        raise ValidationFailedError("Razlog prestanka članstva je obavezan.")

    guard = idempotency.begin(
        db,
        school_id,
        "m07.family.end_member",
        request_id,
        {
            "membership_id": membership_id,
            "expected_version": expected_version,
            "reason_code": reason_code,
            "actor_account_id": actor_account_id,
        },
    )
    if guard.replay is not None:
        return _require_membership(db, school_id, membership_id)

    membership = _require_membership(db, school_id, membership_id)
    if membership.status is not FamilyMembershipStatus.ACTIVE:
        raise InvalidRelationshipTransitionError("Članstvo je već završeno.")
    _check_version(membership.version, expected_version)

    end_date = effective_until or clock.now().date()
    if end_date < membership.effective_from:
        raise ValidationFailedError(
            "Datum prestanka ne može biti pre datuma početka."
        )

    membership.status = FamilyMembershipStatus.ENDED
    membership.effective_until = end_date
    membership.end_reason_code = reason_code
    membership.version += 1
    db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="m07.family.end_member",
        entity_type="family_membership",
        entity_id=membership.id,
        summary="Članstvo u porodičnoj grupi je završeno.",
        school_id=school_id,
        actor_person_id=actor_person_id,
        context={"reason_code": reason_code},
    )
    idempotency.complete(db, guard, status=200, body={"id": membership.id})
    return membership


def _require_membership(
    db: Session, school_id: str, membership_id: str
) -> FamilyMembership:
    membership = db.execute(
        select(FamilyMembership).where(
            FamilyMembership.school_id == school_id,
            FamilyMembership.id == membership_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Članstvo nije pronađeno.")
    return membership


__all__ = [
    "FinancialBlockerPort",
    "add_family_member",
    "archive_family",
    "create_family",
    "end_family_membership",
]
