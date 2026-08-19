from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import BadRequestError, ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.domains.identity.enums import PersonIdentityStatus, PersonMergeStatus
from app.domains.identity.models import Person, PersonMergeRecord
from app.domains.organization.enums import MembershipStatus, OrgMemberType
from app.domains.organization.models import OrganizationMembership
from app.domains.people import repository
from app.domains.people.enums import GuardianAccessStatus, GuardianRelationshipType
from app.domains.people.models import GuardianOrganizationAccess, GuardianRelationship
from app.domains.people.schemas import (
    CreateMergeReviewRequest,
    CreatePersonRequest,
    DuplicateCandidate,
    DuplicateCluster,
    GuardianContactResponse,
    MembershipResponse,
    MembershipTransitionRequest,
    MergeDecisionRequest,
    MergeReviewResponse,
    PersonResponse,
    PersonSummary,
    RevokeGuardianAccessRequest,
    UpdateMemberDataRequest,
)
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext

_LAST_OWNER_ERROR = "Škola mora imati bar jednog aktivnog vlasnika."


def create_provisional_person(
    db: Session, context: RequestContext, req: CreatePersonRequest
) -> PersonResponse:
    """Journey 8. Create a provisional person and attach them to the active org.

    If a same-named member already exists, refuse with a 409 that lists the
    candidates, unless the caller has explicitly confirmed the duplicate with a
    written reason.
    """
    candidates = repository.find_duplicate_candidates(
        db, context.organization_id, req.given_name, req.family_name
    )
    if candidates and not req.allow_possible_duplicate:
        raise ConflictError(
            "Moguć duplikat: osoba sa istim imenom već postoji u ovoj školi.",
            details={
                "code": "POSSIBLE_DUPLICATE",
                "candidates": [
                    {"person_id": p.id, "display_name": p.display_name} for p in candidates
                ],
            },
        )

    given = req.given_name.strip()
    family = req.family_name.strip()
    person = Person(
        given_name=given,
        family_name=family,
        display_name=f"{given} {family}",
        identity_status=PersonIdentityStatus.PROVISIONAL,
    )
    db.add(person)
    db.flush()

    db.add(
        OrganizationMembership(
            organization_id=context.organization_id,
            person_id=person.id,
            member_type=req.member_type,
        )
    )

    summary = f"Dodata osoba „{person.display_name}“."
    if req.allow_possible_duplicate:
        summary += f" Potvrđen mogući duplikat: {req.duplicate_reason}"
    record_audit(
        db,
        data_class=AuditDataClass.IDENTITY,
        action="person.created",
        entity_type="person",
        entity_id=person.id,
        summary=summary,
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"duplicate_override": req.allow_possible_duplicate},
    )
    enqueue(
        db,
        event_type="person.created",
        payload={"person_id": person.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    db.commit()
    return PersonResponse.model_validate(person)


def list_people(
    db: Session,
    context: RequestContext,
    params: PageParams,
    *,
    member_type: OrgMemberType | None = None,
) -> Page[PersonSummary]:
    rows, total = repository.list_org_people(
        db, context.organization_id, params, member_type=member_type
    )
    items = [
        PersonSummary(
            id=person.id,
            display_name=person.display_name,
            identity_status=person.identity_status,
            member_type=kind,
        )
        for person, kind in rows
    ]
    return Page.build(items, total, params)


def get_person(db: Session, context: RequestContext, person_id: str) -> PersonResponse:
    person = repository.get_org_person(db, context.organization_id, person_id)
    if person is None:
        raise NotFoundError("Osoba nije pronađena.")
    return PersonResponse.model_validate(person)


# ---------------------------------------------------------------------------
# Membership lifecycle (§16/§19/§20/§21), end / suspend / resume
# ---------------------------------------------------------------------------


def _load_member(
    db: Session, context: RequestContext, person_id: str
) -> tuple[OrganizationMembership, Person]:
    membership = repository.get_membership(db, context.organization_id, person_id)
    person = repository.get_org_person(db, context.organization_id, person_id)
    if membership is None or person is None:
        # Foreign or nonexistent resource returns the same error, never leak.
        raise NotFoundError("Osoba nije pronađena.")
    return membership, person


def _guard_not_last_owner(db: Session, organization_id: str, person_id: str) -> None:
    """§22, never strip the school of its last remaining active owner."""
    if (
        repository.is_active_owner(db, organization_id, person_id)
        and repository.count_active_owners(db, organization_id) <= 1
    ):
        raise ConflictError(_LAST_OWNER_ERROR)


def _emit_membership_change(
    db: Session,
    context: RequestContext,
    membership: OrganizationMembership,
    person: Person,
    action: str,
    reason: str | None,
) -> None:
    verb = {"ended": "okončano", "suspended": "suspendovano", "resumed": "nastavljeno"}[action]
    summary = f"Članstvo za „{person.display_name}“ je {verb}."
    if reason and reason.strip():
        summary += f" Razlog: {reason.strip()}"
    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action=f"membership.{action}",
        entity_type="organization_membership",
        entity_id=membership.id,
        summary=summary,
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"person_id": person.id},
    )
    enqueue(
        db,
        event_type=f"membership.{action}",
        payload={
            "membership_id": membership.id,
            "person_id": person.id,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )


def get_membership(
    db: Session, context: RequestContext, person_id: str
) -> MembershipResponse:
    membership, _ = _load_member(db, context, person_id)
    return MembershipResponse.model_validate(membership)


def end_membership(
    db: Session, context: RequestContext, person_id: str, req: MembershipTransitionRequest
) -> MembershipResponse:
    membership, person = _load_member(db, context, person_id)
    if membership.status is MembershipStatus.ENDED:
        raise ConflictError("Članstvo je već okončano.")
    _guard_not_last_owner(db, context.organization_id, person_id)
    membership.status = MembershipStatus.ENDED
    _emit_membership_change(db, context, membership, person, "ended", req.reason)
    db.commit()
    return MembershipResponse.model_validate(membership)


def suspend_membership(
    db: Session, context: RequestContext, person_id: str, req: MembershipTransitionRequest
) -> MembershipResponse:
    membership, person = _load_member(db, context, person_id)
    if membership.status is MembershipStatus.ENDED:
        raise ConflictError("Okončano članstvo ne može biti suspendovano.")
    if membership.status is MembershipStatus.SUSPENDED:
        raise ConflictError("Članstvo je već suspendovano.")
    _guard_not_last_owner(db, context.organization_id, person_id)
    membership.status = MembershipStatus.SUSPENDED
    _emit_membership_change(db, context, membership, person, "suspended", req.reason)
    db.commit()
    return MembershipResponse.model_validate(membership)


def resume_membership(
    db: Session, context: RequestContext, person_id: str, req: MembershipTransitionRequest
) -> MembershipResponse:
    membership, person = _load_member(db, context, person_id)
    if membership.status is MembershipStatus.ACTIVE:
        raise ConflictError("Članstvo je već aktivno.")
    if membership.status is MembershipStatus.ENDED:
        # Ended is terminal; reactivation is a new membership, never a revived row.
        raise ConflictError("Okončano članstvo se ne može nastaviti.")
    membership.status = MembershipStatus.ACTIVE
    _emit_membership_change(db, context, membership, person, "resumed", req.reason)
    db.commit()
    return MembershipResponse.model_validate(membership)


# ---------------------------------------------------------------------------
# School-local member data (§8/§9/§10), local code + admin note
# ---------------------------------------------------------------------------


def update_member_data(
    db: Session, context: RequestContext, person_id: str, req: UpdateMemberDataRequest
) -> MembershipResponse:
    membership, person = _load_member(db, context, person_id)
    fields = req.model_fields_set

    if "local_member_code" in fields:
        code = (req.local_member_code or "").strip() or None
        if code is not None and repository.find_local_code_owner(
            db, context.organization_id, code, person_id
        ) is not None:
            raise ConflictError("Lokalna šifra člana se već koristi u ovoj školi.")
        membership.local_member_code = code

    if "admin_note" in fields:
        membership.admin_note = (req.admin_note or "").strip() or None

    if "member_type" in fields and req.member_type is not None:
        membership.member_type = req.member_type

    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="membership.data_updated",
        entity_type="organization_membership",
        entity_id=membership.id,
        summary=f"Ažurirani lokalni podaci člana za „{person.display_name}“.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"person_id": person.id},
    )
    db.commit()
    return MembershipResponse.model_validate(membership)


# ---------------------------------------------------------------------------
# Guardian management (§25 primary contact, §30 revoke access)
# ---------------------------------------------------------------------------


def _relationship_type(
    db: Session, access: GuardianOrganizationAccess
) -> GuardianRelationshipType:
    rel = db.execute(
        select(GuardianRelationship).where(
            GuardianRelationship.guardian_person_id == access.guardian_person_id,
            GuardianRelationship.child_person_id == access.child_person_id,
        )
    ).scalar_one_or_none()
    return rel.relationship_type if rel is not None else GuardianRelationshipType.OTHER


def _contact_response(
    db: Session, access: GuardianOrganizationAccess, guardian: Person
) -> GuardianContactResponse:
    return GuardianContactResponse(
        guardian_person_id=guardian.id,
        display_name=guardian.display_name,
        relationship_type=_relationship_type(db, access),
        access_status=access.status,
        is_primary_contact=access.is_primary_contact,
    )


def list_guardians(
    db: Session, context: RequestContext, person_id: str
) -> list[GuardianContactResponse]:
    child = repository.get_org_person(db, context.organization_id, person_id)
    if child is None:
        raise NotFoundError("Osoba nije pronađena.")
    return [
        GuardianContactResponse(
            guardian_person_id=guardian.id,
            display_name=guardian.display_name,
            relationship_type=(
                rel.relationship_type if rel is not None else GuardianRelationshipType.OTHER
            ),
            access_status=access.status,
            is_primary_contact=access.is_primary_contact,
        )
        for access, guardian, rel in repository.list_guardians_for_child(
            db, context.organization_id, person_id
        )
    ]


def revoke_guardian_access(
    db: Session,
    context: RequestContext,
    person_id: str,
    guardian_person_id: str,
    req: RevokeGuardianAccessRequest,
) -> GuardianContactResponse:
    child = repository.get_org_person(db, context.organization_id, person_id)
    if child is None:
        raise NotFoundError("Osoba nije pronađena.")
    access = repository.get_guardian_access(
        db, context.organization_id, person_id, guardian_person_id
    )
    if access is None:
        raise NotFoundError("Roditeljski pristup nije pronađen.")
    if access.status is GuardianAccessStatus.REVOKED:
        raise ConflictError("Roditeljski pristup je već opozvan.")

    access.status = GuardianAccessStatus.REVOKED
    access.is_primary_contact = False  # a revoked contact can no longer be primary
    guardian = db.get(Person, guardian_person_id)
    assert guardian is not None

    summary = (
        f"Roditeljski pristup osobe „{guardian.display_name}“ za "
        f"„{child.display_name}“ je opozvan."
    )
    if req.reason and req.reason.strip():
        summary += f" Razlog: {req.reason.strip()}"
    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="guardian.access_revoked",
        entity_type="guardian_organization_access",
        entity_id=access.id,
        summary=summary,
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"guardian_person_id": guardian_person_id, "child_person_id": person_id},
    )
    enqueue(
        db,
        event_type="guardian.access_revoked",
        payload={
            "access_id": access.id,
            "guardian_person_id": guardian_person_id,
            "child_person_id": person_id,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )
    db.commit()
    return _contact_response(db, access, guardian)


def set_primary_contact(
    db: Session, context: RequestContext, person_id: str, guardian_person_id: str
) -> GuardianContactResponse:
    child = repository.get_org_person(db, context.organization_id, person_id)
    if child is None:
        raise NotFoundError("Osoba nije pronađena.")
    access = repository.get_guardian_access(
        db, context.organization_id, person_id, guardian_person_id
    )
    if access is None:
        raise NotFoundError("Roditeljski pristup nije pronađen.")
    if access.status is not GuardianAccessStatus.ACTIVE:
        raise ConflictError("Samo aktivan kontakt može biti primarni.")

    guardian = db.get(Person, guardian_person_id)
    assert guardian is not None
    if access.is_primary_contact:
        return _contact_response(db, access, guardian)

    # Exactly one primary per child: demote the current one first (§25).
    for current in repository.child_primary_contacts(db, context.organization_id, person_id):
        current.is_primary_contact = False
    db.flush()
    access.is_primary_contact = True

    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="guardian.primary_set",
        entity_type="guardian_organization_access",
        entity_id=access.id,
        summary=(
            f"„{guardian.display_name}“ je označen/a kao primarni kontakt za "
            f"„{child.display_name}“."
        ),
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"guardian_person_id": guardian_person_id, "child_person_id": person_id},
    )
    db.commit()
    return _contact_response(db, access, guardian)


# ---------------------------------------------------------------------------
# Duplicate detection + review (§13–15)
# ---------------------------------------------------------------------------


def list_duplicates(db: Session, context: RequestContext) -> list[DuplicateCluster]:
    clusters: list[DuplicateCluster] = []
    for given, family in repository.list_duplicate_clusters(db, context.organization_id):
        people = repository.find_duplicate_candidates(
            db, context.organization_id, given, family
        )
        if len(people) > 1:
            clusters.append(
                DuplicateCluster(
                    given_name=given,
                    family_name=family,
                    candidates=[
                        DuplicateCandidate(person_id=p.id, display_name=p.display_name)
                        for p in people
                    ],
                )
            )
    return clusters


def create_merge_review(
    db: Session, context: RequestContext, req: CreateMergeReviewRequest
) -> MergeReviewResponse:
    if req.source_person_id == req.target_person_id:
        raise BadRequestError("Izvor i cilj spajanja moraju biti različite osobe.")
    source = repository.get_org_person(db, context.organization_id, req.source_person_id)
    target = repository.get_org_person(db, context.organization_id, req.target_person_id)
    if source is None or target is None:
        raise NotFoundError("Osoba nije pronađena.")
    if repository.find_open_review(
        db, context.organization_id, source.id, target.id
    ) is not None:
        raise ConflictError("Predmet spajanja za ove osobe je već otvoren.")

    review = PersonMergeRecord(
        organization_id=context.organization_id,
        source_person_id=source.id,
        target_person_id=target.id,
        status=PersonMergeStatus.FLAGGED,
        reason=req.reason.strip(),
        flagged_by_person_id=context.person_id,
    )
    db.add(review)
    db.flush()
    record_audit(
        db,
        data_class=AuditDataClass.IDENTITY,
        action="person.merge_flagged",
        entity_type="person_merge_record",
        entity_id=review.id,
        summary=(
            f"Označen mogući duplikat: „{source.display_name}“ ↔ „{target.display_name}“."
        ),
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"source_person_id": source.id, "target_person_id": target.id},
    )
    db.commit()
    return MergeReviewResponse.model_validate(review)


def list_merge_reviews(db: Session, context: RequestContext) -> list[MergeReviewResponse]:
    return [
        MergeReviewResponse.model_validate(r)
        for r in repository.list_open_merge_reviews(db, context.organization_id)
    ]


def decide_merge_review(
    db: Session, context: RequestContext, review_id: str, req: MergeDecisionRequest
) -> MergeReviewResponse:
    review = repository.get_merge_review(db, context.organization_id, review_id)
    if review is None:
        raise NotFoundError("Predmet spajanja nije pronađen.")
    if review.status is not PersonMergeStatus.FLAGGED:
        raise ConflictError("Predmet spajanja je već rešen.")

    if req.decision == "DISMISS":
        review.status = PersonMergeStatus.DISMISSED
        review.performed_by_person_id = context.person_id
        review.reason = f"{review.reason} | Odbačeno: {req.reason.strip()}"
        record_audit(
            db,
            data_class=AuditDataClass.IDENTITY,
            action="person.merge_dismissed",
            entity_type="person_merge_record",
            entity_id=review.id,
            summary="Predmet spajanja je odbačen: osobe su različite.",
            organization_id=context.organization_id,
            actor_person_id=context.person_id,
        )
        db.commit()
        return MergeReviewResponse.model_validate(review)

    # MERGE, conservative: mark the source merged and end its org membership.
    # Repointing of the source's relationships/payments is a deliberate follow-up.
    source = repository.get_org_person(db, context.organization_id, review.source_person_id)
    target = repository.get_org_person(db, context.organization_id, review.target_person_id)
    if source is None or target is None:
        raise ConflictError("Osobe iz predmeta više nisu dostupne za spajanje.")
    _guard_not_last_owner(db, context.organization_id, source.id)

    source.identity_status = PersonIdentityStatus.MERGED
    source_membership = repository.get_membership(db, context.organization_id, source.id)
    if source_membership is not None:
        source_membership.status = MembershipStatus.ENDED
        source_membership.record_status = RecordStatus.ARCHIVED

    review.status = PersonMergeStatus.MERGED
    review.performed_by_person_id = context.person_id
    review.reason = f"{review.reason} | Spojeno u {target.id}: {req.reason.strip()}"
    record_audit(
        db,
        data_class=AuditDataClass.IDENTITY,
        action="person.merged",
        entity_type="person",
        entity_id=source.id,
        summary=f"„{source.display_name}“ je spojen/a u „{target.display_name}“.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"source_person_id": source.id, "target_person_id": target.id},
    )
    enqueue(
        db,
        event_type="person.merged",
        payload={
            "source_person_id": source.id,
            "target_person_id": target.id,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )
    db.commit()
    return MergeReviewResponse.model_validate(review)
