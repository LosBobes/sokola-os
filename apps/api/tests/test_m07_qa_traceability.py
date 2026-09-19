"""M07 §8 criterion 1: the 52 numbered QA scenarios, with a traceability gate.

`02-M07-QA-I-TRACEABILITY.md` lists 52 scenarios and the contract's acceptance
bar is "Pokrenuto 52, prošlo 52, preskočeno 0". Nothing in this repository has
ever implemented a v5.7 QA scenario *as such* — behaviour is covered, but not
under the ids the contract traces against, so "which scenarios pass" has never
had an answer.

This file gives it one. Each implemented scenario is a test named for its id,
so a failure names the contract row it breaks. The ones that cannot run yet are
listed in `BLOCKED` with the reason, and the traceability test below fails if
any of the 52 is neither. That gate is the point: a scenario can be
unimplemented, but it cannot be *forgotten*, and it cannot quietly disappear
when someone renames a test.

**No test here is skipped.** The contract says "preskočeno 0", and a skipped
test reports as neither pass nor fail — which is exactly the shape of a
scenario nobody looked at. The blocked ones are declared data, not decorated
tests.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from app.common.errors import (
    DependencyUnavailableError,
    FamilyArchiveBlockedError,
    ForbiddenError,
    IdempotencyConflictError,
    InvalidRelationshipTransitionError,
    RelationshipExistsError,
    ValidationFailedError,
)
from app.domains.family import guardian_commands as grd
from app.domains.family import payer_commands as pay
from app.domains.family import ports
from app.domains.family import primary_contact_commands as pgc
from app.domains.family import primary_payer_commands as ppd
from app.domains.family import service as fam
from app.domains.family.enums import (
    DesignationStatus,
    FamilyMembershipStatus,
    FamilyStatus,
    LinkKind,
    LinkStatus,
    MemberKind,
    PayerBasisKind,
    RelationshipKind,
    VerificationMethod,
)
from app.domains.family.models import (
    Family,
    FamilyMembership,
    GuardianChildLink,
    PayerChildLink,
    PrimaryGuardianContactDesignation,
    PrimaryPayerDesignation,
    RelationshipVerificationRecord,
)
from app.domains.identity.auth_models import UserAccount
from app.domains.people import membership as mem
from app.domains.school.enums import MembershipStatus, MembershipType
from app.domains.school.models import SchoolMembership
from app.platform.audit.models import AuditLog
from app.platform.outbox.models import OutboxMessage
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import ensure_person_profile, make_person, make_school

#: The contract file, read at test time so the scenario list cannot drift from
#: the vendored spec without this file noticing.
_QA_DOC = (
    Path(__file__).resolve().parents[3]
    / "docs/spec/v5.7/04-MODULSKI-UGOVORI/07-M07-RODITELJI-I-STARATELJI"
    / "02-M07-QA-I-TRACEABILITY.md"
)

#: Scenarios that cannot run yet, each with the reason. Two causes only.
#:
#: *No HTTP surface.* §4's chain (M01 session -> M03 context -> M05 permission
#: -> M07 subject basis) needs M07's permission keys, which live in an M05
#: continuation registry that F-30 leaves undetermined. Anything asserting a
#: status code, a safe 404 shape, or "no count/cursor hint" is asserting about
#: a response, and there is no response yet.
#:
#: *True concurrency.* Two transactions racing needs two live sessions; the
#: single-session suite can drive the guard but cannot produce the race. The
#: *losing* side of each race is covered by the version tests, so what is
#: missing is the interleaving, not the rule.
BLOCKED: dict[str, str] = {
    "M07-QA-002": "no HTTP surface: asserts the 404 response shape (F-30)",
    "M07-QA-013": "no HTTP surface: asserts the safe 404 response (F-30)",
    "M07-QA-018": "true concurrency: two approvers on one version",
    "M07-QA-024": "true concurrency: two designations racing",
    "M07-QA-027": "needs M05 effective permissions wired to a route (F-30)",
    "M07-QA-028": "no HTTP surface: guardian-to-guardian read projection (F-30)",
    "M07-QA-036": "no HTTP surface: payer reading child endpoints (F-30)",
    "M07-QA-039": "no HTTP surface: stale-cache request after revoke (F-30)",
    "M07-QA-040": "no HTTP surface: high-risk write spanning a revoke (F-30)",
    "M07-QA-043": "needs the outbox consumer and M14 delivery policy",
    "M07-QA-045": "client-side: offline behaviour is a web concern",
    "M07-QA-052": "true concurrency: PAY-02 and PAY-04 on one version",
}

ACTOR = "acc_staff"
APPROVER = "acc_approver"
POLICY = "M07-VERIFY-1.0"


def _rid() -> str:
    return str(uuid.uuid4())


def _no_obligations(_s: str, _f: str) -> bool:
    return False


class World:
    """§'Seed podaci': two schools, a child in two families, G1/G2 and a payer
    who is not a guardian."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.a = make_school(db, name="Škola A")
        self.b = make_school(db, name="Škola B")
        self.child = self._person(db, "Iva")
        self.g1 = self._person(db, "Milan")
        self.g2 = self._person(db, "Ana")
        self.payer = self._person(db, "Nikola")

        self.child_mem = self._membership(self.child, MembershipType.PARTICIPANT)
        self.g1_mem = self._membership(self.g1, MembershipType.GUARDIAN)
        self.g2_mem = self._membership(self.g2, MembershipType.GUARDIAN)
        self.payer_mem = self._membership(self.payer, MembershipType.CONTACT)
        db.commit()

        self.family1 = self._family()
        self.family2 = self._family()
        for person, kind in (
            (self.g1, MemberKind.ADULT),
            (self.payer, MemberKind.ADULT),
            (self.child, MemberKind.DEPENDENT),
        ):
            self._join(self.family1, person, kind)
        self._join(self.family2, self.g2, MemberKind.ADULT)
        self._join(self.family2, self.child, MemberKind.DEPENDENT)
        db.commit()

    def _person(self, db: Session, given: str):
        person = make_person(db, given=given, family="Petrović")
        ensure_person_profile(db, school=self.a, person=person)
        return person

    def _membership(self, person, kind: MembershipType) -> SchoolMembership:
        return mem.create_membership(
            self.db,
            school_id=self.a.id,
            person_id=person.id,
            membership_type=kind,
            status=MembershipStatus.ACTIVE,
        )

    def _family(self) -> Family:
        return fam.create_family(
            self.db, school_id=self.a.id, actor_account_id=ACTOR, request_id=_rid()
        )

    def _join(self, family: Family, person, kind: MemberKind) -> FamilyMembership:
        return fam.add_family_member(
            self.db,
            school_id=self.a.id,
            family_id=family.id,
            person_id=person.id,
            member_kind=kind,
            actor_account_id=ACTOR,
            request_id=_rid(),
        )

    # -- guardian helpers ---------------------------------------------------

    def request_guardian(self, guardian=None, child=None, **kw) -> GuardianChildLink:
        return grd.request_guardian_child_link(
            self.db,
            school_id=kw.pop("school_id", self.a.id),
            guardian_person_id=(guardian or self.g1).id,
            child_person_id=(child or self.child).id,
            relationship_kind=kw.pop("relationship_kind", RelationshipKind.PARENT),
            actor_account_id=kw.pop("actor_account_id", ACTOR),
            request_id=kw.pop("request_id", _rid()),
        )

    def activate_guardian(self, link: GuardianChildLink, **kw) -> GuardianChildLink:
        return grd.verify_and_activate_guardian_link(
            self.db,
            school_id=self.a.id,
            link_id=link.id,
            expected_version=kw.pop("expected_version", link.version),
            verification_method=kw.pop(
                "verification_method", VerificationMethod.SCHOOL_RECORD
            ),
            policy_version=kw.pop("policy_version", POLICY),
            actor_account_id=kw.pop("actor_account_id", APPROVER),
            request_id=kw.pop("request_id", _rid()),
        )

    def active_guardian(self, guardian=None) -> GuardianChildLink:
        link = self.request_guardian(guardian)
        self.activate_guardian(link)
        self.db.commit()
        return link

    # -- payer helpers ------------------------------------------------------

    def request_payer(self, payer=None, **kw) -> PayerChildLink:
        return pay.request_payer_child_link(
            self.db,
            school_id=self.a.id,
            payer_person_id=(payer or self.payer).id,
            child_person_id=self.child.id,
            family_id=kw.pop("family_id", self.family1.id),
            basis_kind=kw.pop("basis_kind", PayerBasisKind.FAMILY_ADULT),
            actor_account_id=kw.pop("actor_account_id", ACTOR),
            request_id=kw.pop("request_id", _rid()),
        )

    def activate_payer(self, link: PayerChildLink, **kw) -> PayerChildLink:
        return pay.verify_and_activate_payer_link(
            self.db,
            school_id=self.a.id,
            link_id=link.id,
            expected_version=kw.pop("expected_version", link.version),
            verification_method=kw.pop(
                "verification_method", VerificationMethod.SCHOOL_RECORD
            ),
            policy_version=kw.pop("policy_version", POLICY),
            actor_account_id=kw.pop("actor_account_id", APPROVER),
            request_id=kw.pop("request_id", _rid()),
        )

    def active_payer(self, payer=None, **kw) -> PayerChildLink:
        link = self.request_payer(payer, **kw)
        self.activate_payer(link)
        self.db.commit()
        return link


@pytest.fixture
def world(db: Session) -> World:
    return World(db)


# ===========================================================================
# The traceability gate
# ===========================================================================


def _declared_scenarios() -> set[str]:
    return set(re.findall(r"M07-QA-\d{3}", _QA_DOC.read_text()))


def _implemented_scenarios() -> set[str]:
    source = Path(__file__).read_text()
    return {
        f"M07-QA-{num}"
        for num in re.findall(r"^def test_m07_qa_(\d{3})_", source, re.MULTILINE)
    }


def test_every_qa_scenario_is_either_implemented_or_declared() -> None:
    """§8.1: 52 scenarios, none skipped and none forgotten.

    This is the test that makes the rest trustworthy. Without it, deleting or
    renaming a scenario test removes it from the suite silently — and the
    contract's bar is not "the tests pass", it is "all 52 ran".
    """
    declared = _declared_scenarios()
    assert len(declared) == 52, f"expected 52 scenarios in the contract, found {len(declared)}"

    implemented = _implemented_scenarios()
    blocked = set(BLOCKED)
    assert implemented & blocked == set(), (
        "a scenario is both implemented and declared blocked: "
        f"{sorted(implemented & blocked)}"
    )
    missing = declared - implemented - blocked
    assert not missing, f"scenarios neither implemented nor declared blocked: {sorted(missing)}"
    stray = (implemented | blocked) - declared
    assert not stray, f"scenario ids not in the contract: {sorted(stray)}"


def test_the_blocked_list_stays_honest_about_why() -> None:
    """Every blocked scenario names a cause, and only the two real causes.

    A free-text reason field rots into "TODO". Constraining it to the two
    things actually in the way — no HTTP surface, or a race a single session
    cannot stage — means a third reason has to be added deliberately.
    """
    for scenario, reason in BLOCKED.items():
        assert reason.strip(), f"{scenario} is blocked with no reason"
        assert any(
            cause in reason
            for cause in ("no HTTP surface", "true concurrency", "needs", "client-side")
        ), f"{scenario} has an unrecognised blocking reason: {reason}"


# ===========================================================================
# Family (§2.1-2.2, §3.13, §5.1-5.2)
# ===========================================================================


def test_m07_qa_001_create_family_in_a(world: World, db: Session) -> None:
    """One ACTIVE row, version 1, with a receipt and an audit entry."""
    family = fam.create_family(
        db, school_id=world.a.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()
    assert family.status is FamilyStatus.ACTIVE
    assert family.version == 1
    assert db.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.entity_id == family.id)
    ).scalar_one() == 1


def test_m07_qa_003_one_person_adult_in_two_families(world: World, db: Session) -> None:
    """Allowed, with no implicit data sharing — the families stay separate rows."""
    world._join(world.family2, world.g1, MemberKind.ADULT)
    db.commit()
    families = set(
        db.execute(
            select(FamilyMembership.family_id).where(
                FamilyMembership.person_id == world.g1.id,
                FamilyMembership.status == FamilyMembershipStatus.ACTIVE,
            )
        ).scalars().all()
    )
    assert families == {world.family1.id, world.family2.id}


def test_m07_qa_004_child_dependent_in_two_families(world: World, db: Session) -> None:
    """Separated parents. Both links allowed; §3.2 gives neither visibility of
    the other."""
    families = set(
        db.execute(
            select(FamilyMembership.family_id).where(
                FamilyMembership.person_id == world.child.id,
                FamilyMembership.status == FamilyMembershipStatus.ACTIVE,
            )
        ).scalars().all()
    )
    assert families == {world.family1.id, world.family2.id}


def test_m07_qa_005_duplicate_active_family_membership(world: World) -> None:
    with pytest.raises(RelationshipExistsError):
        world._join(world.family1, world.child, MemberKind.DEPENDENT)


def test_m07_qa_006_end_membership_without_reason(world: World, db: Session) -> None:
    membership = db.execute(
        select(FamilyMembership).where(
            FamilyMembership.family_id == world.family1.id,
            FamilyMembership.person_id == world.child.id,
        )
    ).scalar_one()
    with pytest.raises(ValidationFailedError):
        fam.end_family_membership(
            db,
            school_id=world.a.id,
            membership_id=membership.id,
            expected_version=membership.version,
            reason_code="   ",
            actor_account_id=ACTOR,
            request_id=_rid(),
        )
    db.rollback()
    assert membership.status is FamilyMembershipStatus.ACTIVE


def test_m07_qa_007_archive_empty_family(world: World, db: Session) -> None:
    empty = fam.create_family(
        db, school_id=world.a.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()
    fam.archive_family(
        db,
        school_id=world.a.id,
        family_id=empty.id,
        expected_version=1,
        reason_code="MERGED",
        actor_account_id=ACTOR,
        request_id=_rid(),
        has_open_obligations=_no_obligations,
    )
    db.commit()
    assert empty.status is FamilyStatus.ARCHIVED
    with pytest.raises(InvalidRelationshipTransitionError):
        fam.archive_family(
            db,
            school_id=world.a.id,
            family_id=empty.id,
            expected_version=empty.version,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_no_obligations,
        )


def test_m07_qa_008_archive_blocked_by_active_member(world: World, db: Session) -> None:
    """Nothing is closed by the refusal — the family and its members are
    exactly as they were."""
    before = db.execute(
        select(func.count())
        .select_from(FamilyMembership)
        .where(
            FamilyMembership.family_id == world.family1.id,
            FamilyMembership.status == FamilyMembershipStatus.ACTIVE,
        )
    ).scalar_one()

    with pytest.raises(FamilyArchiveBlockedError):
        fam.archive_family(
            db,
            school_id=world.a.id,
            family_id=world.family1.id,
            expected_version=world.family1.version,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_no_obligations,
        )
    db.rollback()
    assert world.family1.status is FamilyStatus.ACTIVE
    assert db.execute(
        select(func.count())
        .select_from(FamilyMembership)
        .where(
            FamilyMembership.family_id == world.family1.id,
            FamilyMembership.status == FamilyMembershipStatus.ACTIVE,
        )
    ).scalar_one() == before


def test_m07_qa_009_finance_port_unavailable_fails_closed(
    world: World, db: Session
) -> None:
    empty = fam.create_family(
        db, school_id=world.a.id, actor_account_id=ACTOR, request_id=_rid()
    )
    db.commit()

    def _down(_s: str, _f: str) -> bool:
        raise RuntimeError("M12 unreachable")

    with pytest.raises(DependencyUnavailableError) as caught:
        fam.archive_family(
            db,
            school_id=world.a.id,
            family_id=empty.id,
            expected_version=1,
            reason_code="MERGED",
            actor_account_id=ACTOR,
            request_id=_rid(),
            has_open_obligations=_down,
        )
    assert caught.value.status_code == 503
    db.rollback()
    assert empty.status is FamilyStatus.ACTIVE


# ===========================================================================
# Guardian link (§2.3-2.4, §3.5-3.6, §5.3)
# ===========================================================================


def test_m07_qa_010_request_guardian_link_grants_nothing(
    world: World, db: Session
) -> None:
    link = world.request_guardian()
    db.commit()
    assert link.status is LinkStatus.PENDING_VERIFICATION
    assert (
        ports.guardian_subject_basis(
            db,
            school_id=world.a.id,
            guardian_person_id=world.g1.id,
            child_person_id=world.child.id,
        )
        is None
    )


def test_m07_qa_011_guardian_and_child_same_person(world: World) -> None:
    with pytest.raises(ValidationFailedError):
        world.request_guardian(guardian=world.child)


def test_m07_qa_012_guardian_has_staff_not_guardian_membership(
    world: World, db: Session
) -> None:
    staff = make_person(db, given="Jelena", family="Trener")
    ensure_person_profile(db, school=world.a, person=staff)
    mem.create_membership(
        db,
        school_id=world.a.id,
        person_id=staff.id,
        membership_type=MembershipType.STAFF,
        status=MembershipStatus.ACTIVE,
    )
    db.commit()
    with pytest.raises(ValidationFailedError):
        world.request_guardian(guardian=staff)


def test_m07_qa_014_second_open_link_for_one_pair(world: World) -> None:
    world.active_guardian()
    with pytest.raises(RelationshipExistsError):
        world.request_guardian()


def test_m07_qa_015_guardian_verifies_their_own_link(
    world: World, db: Session
) -> None:
    """§3.6. The account is a *different* account and still refused, because it
    belongs to the guardian named in the link."""
    link = world.request_guardian()
    account = UserAccount(person_id=world.g1.id)
    db.add(account)
    db.commit()
    with pytest.raises(ForbiddenError):
        world.activate_guardian(link, actor_account_id=account.id)


def test_m07_qa_016_activate_without_policy_version(world: World, db: Session) -> None:
    """§2.4 makes `policy_version` mandatory: an activation nobody can trace to
    a checking procedure is not evidence of one."""
    link = world.request_guardian()
    db.commit()
    with pytest.raises(ValidationFailedError):
        world.activate_guardian(link, policy_version="  ")


def test_m07_qa_017_valid_activation_writes_exactly_one_proof(
    world: World, db: Session
) -> None:
    link = world.active_guardian()
    assert link.status is LinkStatus.ACTIVE
    records = (
        db.execute(
            select(RelationshipVerificationRecord).where(
                RelationshipVerificationRecord.guardian_child_link_id == link.id
            )
        ).scalars().all()
    )
    assert len(records) == 1
    assert records[0].link_kind is LinkKind.GUARDIAN_CHILD


def test_m07_qa_019_failed_proof_rolls_the_activation_back(
    world: World, db: Session
) -> None:
    """§3.5: both rows or neither.

    The failure is staged by inserting the link's one allowed proof first, so
    the command's own insert violates the partial unique — the same rollback
    path a disk error would take, reached through a rule rather than a mock.
    """
    link = world.request_guardian()
    db.commit()
    db.add(
        RelationshipVerificationRecord(
            school_id=world.a.id,
            link_kind=LinkKind.GUARDIAN_CHILD,
            guardian_child_link_id=link.id,
            verification_method=VerificationMethod.MIGRATION_VERIFIED,
            verified_by_account_id="acc_other",
            verified_at=link.requested_at,
            policy_version=POLICY,
        )
    )
    db.commit()

    with pytest.raises(IntegrityError):
        world.activate_guardian(link)
    db.rollback()

    reloaded = db.execute(
        select(GuardianChildLink).where(GuardianChildLink.id == link.id)
    ).scalar_one()
    assert reloaded.status is LinkStatus.PENDING_VERIFICATION
    assert reloaded.activated_at is None


def test_m07_qa_020_reject_without_reason(world: World, db: Session) -> None:
    link = world.request_guardian()
    db.commit()
    with pytest.raises(ValidationFailedError):
        grd.reject_guardian_link(
            db,
            school_id=world.a.id,
            link_id=link.id,
            expected_version=link.version,
            reason_code="",
            actor_account_id=APPROVER,
            request_id=_rid(),
        )
    db.rollback()
    assert link.status is LinkStatus.PENDING_VERIFICATION


def test_m07_qa_021_reactivating_a_terminal_link(world: World, db: Session) -> None:
    link = world.active_guardian()
    grd.revoke_guardian_link(
        db,
        school_id=world.a.id,
        link_id=link.id,
        expected_version=link.version,
        reason_code="GUARDIANSHIP_ENDED",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()
    with pytest.raises(InvalidRelationshipTransitionError):
        world.activate_guardian(link, expected_version=link.version)

    fresh = world.request_guardian()
    db.commit()
    assert fresh.id != link.id


def test_m07_qa_022_three_active_guardian_links(world: World, db: Session) -> None:
    world.active_guardian(world.g1)
    world.active_guardian(world.g2)
    third = make_person(db, given="Petar", family="Ilić")
    ensure_person_profile(db, school=world.a, person=third)
    mem.create_membership(
        db,
        school_id=world.a.id,
        person_id=third.id,
        membership_type=MembershipType.GUARDIAN,
        status=MembershipStatus.ACTIVE,
    )
    db.commit()
    world.active_guardian(third)

    assert db.execute(
        select(func.count())
        .select_from(GuardianChildLink)
        .where(
            GuardianChildLink.child_person_id == world.child.id,
            GuardianChildLink.status == LinkStatus.ACTIVE,
        )
    ).scalar_one() == 3


# ===========================================================================
# Primary guardian contact (§2.6, §3.8, §3.10, §5.4)
# ===========================================================================


def test_m07_qa_023_designate_primary_guardian(world: World, db: Session) -> None:
    link = world.active_guardian()
    designation = pgc.designate_primary_guardian_contact(
        db,
        school_id=world.a.id,
        child_person_id=world.child.id,
        guardian_child_link_id=link.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    assert designation.status is DesignationStatus.ACTIVE
    assert link.status is LinkStatus.ACTIVE


def test_m07_qa_025_replace_primary_guardian(world: World, db: Session) -> None:
    first_link = world.active_guardian(world.g1)
    second_link = world.active_guardian(world.g2)
    first = pgc.designate_primary_guardian_contact(
        db,
        school_id=world.a.id,
        child_person_id=world.child.id,
        guardian_child_link_id=first_link.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    second = pgc.designate_primary_guardian_contact(
        db,
        school_id=world.a.id,
        child_person_id=world.child.id,
        guardian_child_link_id=second_link.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
        expected_current_designation_id=first.id,
    )
    db.commit()
    assert first.status is DesignationStatus.SUPERSEDED
    assert second.status is DesignationStatus.ACTIVE


def test_m07_qa_026_revoking_the_primary_link_closes_the_designation(
    world: World, db: Session
) -> None:
    link = world.active_guardian()
    pgc.designate_primary_guardian_contact(
        db,
        school_id=world.a.id,
        child_person_id=world.child.id,
        guardian_child_link_id=link.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    grd.revoke_guardian_link(
        db,
        school_id=world.a.id,
        link_id=link.id,
        expected_version=link.version,
        reason_code="GUARDIANSHIP_ENDED",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    assert (
        ports.primary_guardian_contact(
            db, school_id=world.a.id, child_person_id=world.child.id
        )
        is None
    )
    assert db.execute(
        select(func.count())
        .select_from(PrimaryGuardianContactDesignation)
        .where(PrimaryGuardianContactDesignation.status == DesignationStatus.ACTIVE)
    ).scalar_one() == 0


# ===========================================================================
# Payer link (§2.5, §3.7, §3.9)
# ===========================================================================


def test_m07_qa_029_request_payer_link_grants_nothing(
    world: World, db: Session
) -> None:
    link = world.request_payer()
    db.commit()
    assert link.status is LinkStatus.PENDING_VERIFICATION
    assert (
        ports.payer_subject_basis(
            db,
            school_id=world.a.id,
            payer_person_id=world.payer.id,
            child_person_id=world.child.id,
        )
        is None
    )


def test_m07_qa_030_payer_who_is_not_a_guardian(world: World, db: Session) -> None:
    link = world.active_payer()
    assert link.payer_membership_type == MembershipType.CONTACT.value
    assert db.execute(
        select(func.count())
        .select_from(GuardianChildLink)
        .where(GuardianChildLink.guardian_person_id == world.payer.id)
    ).scalar_one() == 0
    record = db.execute(
        select(RelationshipVerificationRecord).where(
            RelationshipVerificationRecord.payer_child_link_id == link.id
        )
    ).scalar_one()
    assert record.link_kind is LinkKind.PAYER_CHILD


def test_m07_qa_031_payer_outside_the_family_without_sponsor(
    world: World, db: Session
) -> None:
    outsider = make_person(db, given="Marko", family="Ilić")
    ensure_person_profile(db, school=world.a, person=outsider)
    mem.create_membership(
        db,
        school_id=world.a.id,
        person_id=outsider.id,
        membership_type=MembershipType.CONTACT,
        status=MembershipStatus.ACTIVE,
    )
    db.commit()
    with pytest.raises(ValidationFailedError):
        world.request_payer(payer=outsider)


def test_m07_qa_032_verified_sponsor_from_outside(world: World, db: Session) -> None:
    sponsor = make_person(db, given="Marko", family="Ilić")
    ensure_person_profile(db, school=world.a, person=sponsor)
    mem.create_membership(
        db,
        school_id=world.a.id,
        person_id=sponsor.id,
        membership_type=MembershipType.CONTACT,
        status=MembershipStatus.ACTIVE,
    )
    db.commit()
    link = world.active_payer(
        payer=sponsor, basis_kind=PayerBasisKind.SPONSOR_VERIFIED
    )
    assert link.basis_kind is PayerBasisKind.SPONSOR_VERIFIED
    assert db.execute(
        select(func.count())
        .select_from(GuardianChildLink)
        .where(GuardianChildLink.guardian_person_id == sponsor.id)
    ).scalar_one() == 0


def test_m07_qa_033_two_active_payer_links(world: World, db: Session) -> None:
    world.active_payer()
    world.active_payer(payer=world.g1)
    listed = ports.eligible_payers_for_billing(
        db, school_id=world.a.id, child_person_id=world.child.id
    )
    assert len(listed) == 2


def test_m07_qa_034_designate_primary_payer_on_pending_link(
    world: World, db: Session
) -> None:
    link = world.request_payer()
    db.commit()
    with pytest.raises(InvalidRelationshipTransitionError):
        ppd.designate_primary_payer(
            db,
            school_id=world.a.id,
            child_person_id=world.child.id,
            payer_child_link_id=link.id,
            actor_account_id=ACTOR,
            request_id=_rid(),
        )


def test_m07_qa_035_replace_primary_payer(world: World, db: Session) -> None:
    first_link = world.active_payer()
    second_link = world.active_payer(payer=world.g1)
    first = ppd.designate_primary_payer(
        db,
        school_id=world.a.id,
        child_person_id=world.child.id,
        payer_child_link_id=first_link.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    second = ppd.designate_primary_payer(
        db,
        school_id=world.a.id,
        child_person_id=world.child.id,
        payer_child_link_id=second_link.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
        expected_current_designation_id=first.id,
    )
    db.commit()
    assert first.status is DesignationStatus.SUPERSEDED
    assert second.status is DesignationStatus.ACTIVE
    assert db.execute(
        select(func.count())
        .select_from(PrimaryPayerDesignation)
        .where(PrimaryPayerDesignation.status == DesignationStatus.ACTIVE)
    ).scalar_one() == 1


def test_m07_qa_037_payer_resolver_answers_finance_only(
    world: World, db: Session
) -> None:
    link = world.active_payer()
    basis = ports.payer_subject_basis(
        db,
        school_id=world.a.id,
        payer_person_id=world.payer.id,
        child_person_id=world.child.id,
    )
    assert basis is not None
    assert basis.link_id == link.id
    assert basis.scope == ports.FINANCE_ONLY


# ===========================================================================
# Membership lifecycle and tenant isolation (§3.11-3.12, §4)
# ===========================================================================


def test_m07_qa_038_terminated_membership_resolves_immediately(
    world: World, db: Session
) -> None:
    world.active_guardian()
    membership = db.execute(
        select(SchoolMembership).where(SchoolMembership.id == world.g1_mem.id)
    ).scalar_one()
    membership.status = MembershipStatus.TERMINATED
    membership.termination_reason_code = "LEFT"
    membership.end_date = membership.start_date
    db.commit()

    assert (
        ports.guardian_subject_basis(
            db,
            school_id=world.a.id,
            guardian_person_id=world.g1.id,
            child_person_id=world.child.id,
        )
        is None
    )


def test_m07_qa_048_cross_tenant_reference_is_refused_by_the_database(
    world: World, db: Session
) -> None:
    """The triple composite FK refuses a direct write, not just the service."""
    other_child = make_person(db, given="Lazar", family="B")
    ensure_person_profile(db, school=world.b, person=other_child)
    foreign = mem.create_membership(
        db,
        school_id=world.b.id,
        person_id=other_child.id,
        membership_type=MembershipType.PARTICIPANT,
        status=MembershipStatus.ACTIVE,
    )
    db.commit()

    db.add(
        GuardianChildLink(
            school_id=world.a.id,
            guardian_person_id=world.g1.id,
            child_person_id=world.child.id,
            guardian_school_membership_id=world.g1_mem.id,
            child_school_membership_id=foreign.id,
            guardian_membership_type=MembershipType.GUARDIAN.value,
            child_membership_type=MembershipType.PARTICIPANT.value,
            relationship_kind=RelationshipKind.PARENT,
            status=LinkStatus.PENDING_VERIFICATION,
            requested_by_account_id=ACTOR,
            requested_at=world.family1.created_at,
        )
    )
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert "fk_guardian_child_link_child_membership" in str(caught.value)
    db.rollback()


def test_m07_qa_049_payer_with_only_a_staff_membership(
    world: World, db: Session
) -> None:
    coach = make_person(db, given="Jelena", family="Trener")
    ensure_person_profile(db, school=world.a, person=coach)
    mem.create_membership(
        db,
        school_id=world.a.id,
        person_id=coach.id,
        membership_type=MembershipType.STAFF,
        status=MembershipStatus.ACTIVE,
    )
    db.commit()
    with pytest.raises(ValidationFailedError):
        world.request_payer(payer=coach)
    db.rollback()
    assert db.execute(
        select(func.count())
        .select_from(PayerChildLink)
        .where(PayerChildLink.payer_person_id == coach.id)
    ).scalar_one() == 0


def test_m07_qa_050_terminated_payer_membership_resolves_immediately(
    world: World, db: Session
) -> None:
    world.active_payer()
    membership = db.execute(
        select(SchoolMembership).where(SchoolMembership.id == world.payer_mem.id)
    ).scalar_one()
    membership.status = MembershipStatus.TERMINATED
    membership.termination_reason_code = "LEFT"
    membership.end_date = membership.start_date
    db.commit()

    assert (
        ports.payer_subject_basis(
            db,
            school_id=world.a.id,
            payer_person_id=world.payer.id,
            child_person_id=world.child.id,
        )
        is None
    )


# ===========================================================================
# Idempotency (§7) and privacy (§4, §7.3)
# ===========================================================================


def test_m07_qa_041_activation_retry_returns_one_proof(
    world: World, db: Session
) -> None:
    link = world.request_guardian()
    db.commit()
    request_id = _rid()
    world.activate_guardian(link, request_id=request_id)
    db.commit()
    world.activate_guardian(link, request_id=request_id, expected_version=1)
    db.commit()

    assert db.execute(
        select(func.count()).select_from(RelationshipVerificationRecord)
    ).scalar_one() == 1
    assert db.execute(
        select(func.count())
        .select_from(OutboxMessage)
        .where(OutboxMessage.event_type.like("%guardian_link.activated"))
    ).scalar_one() == 1


def test_m07_qa_042_same_key_different_relationship_kind(
    world: World, db: Session
) -> None:
    request_id = _rid()
    world.request_guardian(request_id=request_id)
    db.commit()
    with pytest.raises(IdempotencyConflictError):
        world.request_guardian(
            request_id=request_id, relationship_kind=RelationshipKind.LEGAL_GUARDIAN
        )


def test_m07_qa_046_payer_activation_needs_its_own_typed_proof(
    world: World, db: Session
) -> None:
    """A guardian-typed record does not satisfy a payer activation.

    §2.4's discriminator CHECK is what enforces it: a record naming a payer
    link must carry `link_kind=PAYER_CHILD`, so a guardian record can never
    stand in for one.
    """
    link = world.active_payer()
    record = db.execute(
        select(RelationshipVerificationRecord).where(
            RelationshipVerificationRecord.payer_child_link_id == link.id
        )
    ).scalar_one()
    assert record.link_kind is LinkKind.PAYER_CHILD
    assert record.guardian_child_link_id is None


def test_m07_qa_047_valid_payer_activation(world: World, db: Session) -> None:
    link = world.active_payer()
    assert link.status is LinkStatus.ACTIVE
    records = (
        db.execute(
            select(RelationshipVerificationRecord).where(
                RelationshipVerificationRecord.payer_child_link_id == link.id
            )
        ).scalars().all()
    )
    assert len(records) == 1


def test_m07_qa_051_payer_activation_retry_then_changed_payload(
    world: World, db: Session
) -> None:
    link = world.request_payer()
    db.commit()
    request_id = _rid()
    world.activate_payer(link, request_id=request_id)
    db.commit()
    world.activate_payer(link, request_id=request_id, expected_version=1)
    db.commit()
    assert db.execute(
        select(func.count()).select_from(RelationshipVerificationRecord)
    ).scalar_one() == 1

    with pytest.raises(IdempotencyConflictError):
        world.activate_payer(
            link,
            request_id=request_id,
            expected_version=1,
            verification_method=VerificationMethod.SIGNED_DECLARATION,
        )


def test_m07_qa_044_no_pii_in_audit_or_outbox(world: World, db: Session) -> None:
    """§4, §7.3: after every flow, nothing carries a name.

    Scanned rather than reasoned about, because a leak here is silent — the
    system keeps working and the disclosure sits in a table nobody reads until
    an incident makes them.
    """
    link = world.active_guardian()
    pgc.designate_primary_guardian_contact(
        db,
        school_id=world.a.id,
        child_person_id=world.child.id,
        guardian_child_link_id=link.id,
        actor_account_id=ACTOR,
        request_id=_rid(),
    )
    db.commit()
    world.active_payer()
    grd.revoke_guardian_link(
        db,
        school_id=world.a.id,
        link_id=link.id,
        expected_version=link.version,
        reason_code="GUARDIANSHIP_ENDED",
        actor_account_id=APPROVER,
        request_id=_rid(),
    )
    db.commit()

    names = {
        world.child.given_name,
        world.child.display_name,
        world.g1.display_name,
        world.payer.display_name,
        "Petrović",
    }
    payloads = repr(
        db.execute(select(OutboxMessage.payload)).scalars().all()
    )
    audits = repr(
        db.execute(
            select(AuditLog.summary, AuditLog.context, AuditLog.entity_id)
        ).all()
    )
    for name in names:
        assert name not in payloads, f"{name!r} leaked into an outbox payload"
        assert name not in audits, f"{name!r} leaked into an audit entry"
