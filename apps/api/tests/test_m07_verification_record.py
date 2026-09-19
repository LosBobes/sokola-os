"""M07 §2.4: the proof behind an activated link, and what it must not hold.

Two things are being protected here, and they pull in different directions.

The first is that a link cannot be activated without exactly one proof (§3.5,
§5.3) — so the schema has to *insist* on the record existing, and on there
being only one per link.

The second is that the proof itself reveals nothing. §2.4 permits a keyed HMAC
of the school's own case reference and forbids "broj dokumenta, ime ili hash
niskoentropijskog PII-ja". Those are one rule, not two: a plain hash of a
national ID number is the number, because the format is short, structured and
often checksummed. The tests below make that concrete rather than taking it on
faith.
"""

from __future__ import annotations

import hashlib

import pytest
from app.domains.family.enums import (
    FamilyStatus,
    LinkKind,
    LinkStatus,
    RelationshipKind,
    VerificationMethod,
)
from app.domains.family.evidence import evidence_reference_digest
from app.domains.family.models import (
    Family,
    GuardianChildLink,
    PayerChildLink,
    RelationshipVerificationRecord,
)
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipType
from app.platform import clock
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school

_SECRET = "test-session-secret"


class _Case:
    """A school with an ACTIVE guardian link and an ACTIVE payer link."""

    def __init__(self, db: Session, *, name: str = "Klub Soko") -> None:
        self.school = make_school(db, name=name)
        self.adult = make_person(db, given="Milan", family="Petrović")
        self.child = make_person(db, given="Iva", family="Petrović")
        ensure_person_profile(db, school=self.school, person=self.adult)
        ensure_person_profile(db, school=self.school, person=self.child)
        guardian_membership = mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.adult.id,
            membership_type=MembershipType.GUARDIAN,
        )
        child_membership = mem.create_membership(
            db,
            school_id=self.school.id,
            person_id=self.child.id,
            membership_type=MembershipType.PARTICIPANT,
        )
        family = Family(
            school_id=self.school.id,
            status=FamilyStatus.ACTIVE,
            created_by_account_id="acc_staff",
        )
        db.add(family)
        db.flush()

        self.guardian_link = GuardianChildLink(
            school_id=self.school.id,
            guardian_person_id=self.adult.id,
            child_person_id=self.child.id,
            guardian_school_membership_id=guardian_membership.id,
            child_school_membership_id=child_membership.id,
            guardian_membership_type=MembershipType.GUARDIAN.value,
            child_membership_type=MembershipType.PARTICIPANT.value,
            relationship_kind=RelationshipKind.PARENT,
            status=LinkStatus.ACTIVE,
            activated_at=clock.now(),
            decision_by_account_id="acc_approver",
            requested_by_account_id="acc_requester",
            requested_at=clock.now(),
        )
        self.payer_link = PayerChildLink(
            school_id=self.school.id,
            payer_person_id=self.adult.id,
            child_person_id=self.child.id,
            payer_school_membership_id=guardian_membership.id,
            child_school_membership_id=child_membership.id,
            payer_membership_type=MembershipType.GUARDIAN.value,
            child_membership_type=MembershipType.PARTICIPANT.value,
            family_id=family.id,
            basis_kind="FAMILY_ADULT",
            status=LinkStatus.ACTIVE,
            activated_at=clock.now(),
            decision_by_account_id="acc_approver",
            requested_by_account_id="acc_requester",
            requested_at=clock.now(),
        )
        db.add_all([self.guardian_link, self.payer_link])
        db.commit()


def _record(case: _Case, **overrides: object) -> RelationshipVerificationRecord:
    fields: dict[str, object] = {
        "school_id": case.school.id,
        "link_kind": LinkKind.GUARDIAN_CHILD,
        "guardian_child_link_id": case.guardian_link.id,
        "verification_method": VerificationMethod.IN_PERSON_DOCUMENT_CHECK,
        "verified_by_account_id": "acc_approver",
        "verified_at": clock.now(),
        "policy_version": "M07-VERIFY-1.0",
    }
    fields.update(overrides)
    return RelationshipVerificationRecord(**fields)


def _refused(
    db: Session, record: RelationshipVerificationRecord, constraint: str
) -> None:
    db.add(record)
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert constraint in str(caught.value), (
        f"expected {constraint} to refuse this row, got: {caught.value}"
    )
    db.rollback()


# ---------------------------------------------------------------------------
# The digest: keyed, and why that is the whole point (§2.4)
# ---------------------------------------------------------------------------


def test_the_digest_is_not_recoverable_by_hashing_the_reference(db: Session) -> None:
    """The concrete reason §2.4 says *keyed*.

    An unkeyed digest of a case reference is reversible for anything with a
    small input space, which is exactly what identity-document numbers have.
    This test does what an attacker with the database would do — hash the
    candidate — and shows it does not match.
    """
    reference = "PREDMET-2026-0041"
    stored = evidence_reference_digest(reference, school_id="org_x", secret=_SECRET)

    assert stored != hashlib.sha256(reference.encode()).hexdigest()
    assert len(stored) == 64
    assert stored == evidence_reference_digest(
        reference, school_id="org_x", secret=_SECRET
    )


def test_one_reference_digests_differently_at_two_schools() -> None:
    """Otherwise the column is a cross-tenant correlation handle.

    §4 goes out of its way to stop one school learning anything about another.
    A digest that ignored the tenant would let anyone holding two schools' rows
    line up the families they have in common.
    """
    reference = "PREDMET-2026-0041"
    assert evidence_reference_digest(
        reference, school_id="org_a", secret=_SECRET
    ) != evidence_reference_digest(reference, school_id="org_b", secret=_SECRET)


def test_a_different_key_yields_a_different_digest() -> None:
    reference = "PREDMET-2026-0041"
    assert evidence_reference_digest(
        reference, school_id="org_a", secret=_SECRET
    ) != evidence_reference_digest(reference, school_id="org_a", secret="other-secret")


def test_a_raw_reference_cannot_be_stored_in_the_digest_column(db: Session) -> None:
    """The shape CHECK, which is what catches the mistake this module is most
    exposed to: putting the case reference itself where its digest belongs."""
    case = _Case(db)
    _refused(
        db,
        _record(case, evidence_reference_digest="PREDMET-2026-0041"),
        "ck_relationship_verification_digest_shape",
    )


def test_the_digest_is_optional(db: Session) -> None:
    """§2.4 makes it optional, and `SCHOOL_RECORD` is why: a school that
    already held the relationship has no case reference to point at."""
    case = _Case(db)
    db.add(
        _record(
            case,
            verification_method=VerificationMethod.SCHOOL_RECORD,
            evidence_reference_digest=None,
        )
    )
    db.commit()

    stored = db.execute(select(RelationshipVerificationRecord)).scalar_one()
    assert stored.evidence_reference_digest is None


# ---------------------------------------------------------------------------
# Exactly one proof per link (§2.4, §5.3)
# ---------------------------------------------------------------------------


def test_a_link_may_hold_only_one_proof(db: Session) -> None:
    case = _Case(db)
    db.add(_record(case))
    db.commit()

    _refused(db, _record(case), "uq_relationship_verification_guardian_link")


def test_a_guardian_and_a_payer_link_each_hold_their_own(db: Session) -> None:
    """The two partial uniques are independent: one adult may be both this
    child's guardian and its payer, and each link is verified separately."""
    case = _Case(db)
    db.add(_record(case))
    db.add(
        _record(
            case,
            link_kind=LinkKind.PAYER_CHILD,
            guardian_child_link_id=None,
            payer_child_link_id=case.payer_link.id,
        )
    )
    db.commit()

    assert (
        db.execute(
            select(func.count()).select_from(RelationshipVerificationRecord)
        ).scalar_one()
        == 2
    )


@pytest.mark.parametrize(
    ("overrides", "why", "constraint"),
    [
        (
            # PAYER_CHILD, so that the discriminator CHECK is *satisfied* by
            # the guardian column being empty and "exactly one" is the only
            # rule left to break. With GUARDIAN_CHILD this row would be
            # refused for the wrong reason.
            {"link_kind": LinkKind.PAYER_CHILD, "guardian_child_link_id": None},
            "no link at all",
            "ck_relationship_verification_one_link",
        ),
        (
            {"payer_child_link_id": "will-be-replaced"},
            "both links at once",
            "ck_relationship_verification_one_link",
        ),
        (
            {
                "link_kind": LinkKind.PAYER_CHILD,
                "guardian_child_link_id": "will-be-replaced",
            },
            "a PAYER_CHILD record holding a guardian link",
            "ck_relationship_verification_link_kind",
        ),
    ],
)
def test_the_discriminator_and_the_links_must_agree(
    db: Session, overrides: dict[str, object], why: str, constraint: str
) -> None:
    """§2.4: "CHECK zahteva tačno jedan link FK u skladu sa `link_kind`".

    Both halves are needed, which the three cases show: "exactly one" alone
    would let a PAYER_CHILD record hold a guardian link, and the agreement
    clause alone would let a record hold both or neither.
    """
    case = _Case(db)
    resolved = {
        key: (
            case.payer_link.id
            if key == "payer_child_link_id" and value == "will-be-replaced"
            else case.guardian_link.id
            if key == "guardian_child_link_id" and value == "will-be-replaced"
            else value
        )
        for key, value in overrides.items()
    }
    _refused(db, _record(case, **resolved), constraint)


# ---------------------------------------------------------------------------
# Tenant safety and lifetime (§4, §2.4)
# ---------------------------------------------------------------------------


def test_a_record_may_not_reach_into_another_schools_link(db: Session) -> None:
    case = _Case(db, name="Klub Soko")
    other = _Case(db, name="Klub Lav")

    _refused(
        db,
        _record(case, guardian_child_link_id=other.guardian_link.id),
        "fk_relationship_verification_guardian_link",
    )


def test_deleting_a_link_takes_its_proof(db: Session) -> None:
    """`CASCADE`, unlike the links' own RESTRICT keys.

    The record has no meaning apart from the link it proves — it is not an
    independent audit row, it is that link's evidence. §5.3 keeps the *history*
    by making a revoked link terminal and a fresh check a new row, so a link is
    never deleted in the ordinary course; if one does go, its proof proves
    nothing and has nothing left to be attached to.
    """
    case = _Case(db)
    db.add(_record(case))
    db.commit()

    link_id = case.guardian_link.id
    db.delete(
        db.execute(
            select(GuardianChildLink).where(GuardianChildLink.id == link_id)
        ).scalar_one()
    )
    db.commit()

    assert (
        db.execute(
            select(func.count()).select_from(RelationshipVerificationRecord)
        ).scalar_one()
        == 0
    )
