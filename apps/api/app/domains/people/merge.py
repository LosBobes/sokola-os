"""Duplicate detection and person merge (§13–15, M06 §2.7).

Split out of ``service.py`` because a merge is a different kind of operation
from the rest of people management: it is the one that *destroys* a record, and
§3.15 wants it as a single transaction that locks both people in a stable id
order, re-parents their tenant-local rows, writes history and only then marks
the loser. Keeping it beside the CRUD invited the two to share helpers that
should not be shared.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import BadRequestError, ConflictError, NotFoundError
from app.domains.identity.enums import PersonIdentityStatus, PersonMergeStatus
from app.domains.identity.models import PersonMergeRecord
from app.domains.people import membership as membership_service
from app.domains.people import repository
from app.domains.people.schemas import (
    CreateMergeReviewRequest,
    DuplicateCandidate,
    DuplicateCluster,
    MergeDecisionRequest,
    MergeReviewResponse,
)
from app.domains.people.service import _guard_not_last_owner
from app.domains.school.enums import MembershipStatus
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def list_duplicates(db: Session, context: RequestContext) -> list[DuplicateCluster]:
    clusters: list[DuplicateCluster] = []
    for given, family in repository.list_duplicate_clusters(db, context.school_id):
        people = repository.find_duplicate_candidates(
            db, context.school_id, given, family
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
    source = repository.get_school_person(db, context.school_id, req.source_person_id)
    target = repository.get_school_person(db, context.school_id, req.target_person_id)
    if source is None or target is None:
        raise NotFoundError("Osoba nije pronađena.")
    if repository.find_open_review(
        db, context.school_id, source.id, target.id
    ) is not None:
        raise ConflictError("Predmet spajanja za ove osobe je već otvoren.")

    review = PersonMergeRecord(
        school_id=context.school_id,
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
        school_id=context.school_id,
        actor_person_id=context.person_id,
        context={"source_person_id": source.id, "target_person_id": target.id},
    )
    db.commit()
    return MergeReviewResponse.model_validate(review)


def list_merge_reviews(db: Session, context: RequestContext) -> list[MergeReviewResponse]:
    return [
        MergeReviewResponse.model_validate(r)
        for r in repository.list_open_merge_reviews(db, context.school_id)
    ]


def decide_merge_review(
    db: Session, context: RequestContext, review_id: str, req: MergeDecisionRequest
) -> MergeReviewResponse:
    review = repository.get_merge_review(db, context.school_id, review_id)
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
            school_id=context.school_id,
            actor_person_id=context.person_id,
        )
        db.commit()
        return MergeReviewResponse.model_validate(review)

    # MERGE, conservative: mark the source merged and end its org membership.
    # Repointing of the source's relationships/payments is a deliberate follow-up.
    source = repository.get_school_person(db, context.school_id, review.source_person_id)
    target = repository.get_school_person(db, context.school_id, review.target_person_id)
    if source is None or target is None:
        raise ConflictError("Osobe iz predmeta više nisu dostupne za spajanje.")
    _guard_not_last_owner(db, context.school_id, source.id)

    source.identity_status = PersonIdentityStatus.MERGED
    source_membership = repository.get_membership(db, context.school_id, source.id)
    if source_membership is not None:
        if source_membership.status is not MembershipStatus.TERMINATED:
            membership_service.terminate_membership(
                db, source_membership, reason_code="MERGED_INTO_ANOTHER_PERSON"
            )
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
        school_id=context.school_id,
        actor_person_id=context.person_id,
        context={"source_person_id": source.id, "target_person_id": target.id},
    )
    enqueue(
        db,
        event_type="person.merged",
        payload={
            "source_person_id": source.id,
            "target_person_id": target.id,
            "school_id": context.school_id,
        },
        school_id=context.school_id,
    )
    db.commit()
    return MergeReviewResponse.model_validate(review)
