from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.common.pagination import Page, PageParams, page_params
from app.domains.organization.enums import OrgMemberType
from app.domains.people import service
from app.domains.people.schemas import (
    CreateMergeReviewRequest,
    CreatePersonRequest,
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
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["people"])

# Staff who may manage the roster.
_staff = require_permission(PermissionArea.PEOPLE)
StaffContext = Annotated[ContextDep, Depends(_staff)]


@router.post(
    "/people",
    response_model=PersonResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPerson",
    responses={409: {"description": "Possible duplicate; confirm to override."}},
)
def create_person(
    body: CreatePersonRequest, db: DbDep, context: StaffContext
) -> PersonResponse:
    return service.create_provisional_person(db, context, body)


@router.get("/people", response_model=Page[PersonSummary], operation_id="listPeople")
def list_people(
    db: DbDep,
    context: ContextDep,
    params: Annotated[PageParams, Depends(page_params)],
    member_type: Annotated[OrgMemberType | None, Query()] = None,
) -> Page[PersonSummary]:
    return service.list_people(db, context, params, member_type=member_type)


# --- Duplicate detection + review (§13–15). Declared before /people/{person_id}
#     so the literal path segments win over the id path parameter. ---


@router.get(
    "/people/duplicates",
    response_model=list[DuplicateCluster],
    operation_id="listDuplicatePeople",
)
def list_duplicate_people(db: DbDep, context: StaffContext) -> list[DuplicateCluster]:
    return service.list_duplicates(db, context)


@router.get(
    "/people/merge-reviews",
    response_model=list[MergeReviewResponse],
    operation_id="listMergeReviews",
)
def list_merge_reviews(db: DbDep, context: StaffContext) -> list[MergeReviewResponse]:
    return service.list_merge_reviews(db, context)


@router.post(
    "/people/merge-reviews",
    response_model=MergeReviewResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createMergeReview",
)
def create_merge_review(
    body: CreateMergeReviewRequest, db: DbDep, context: StaffContext
) -> MergeReviewResponse:
    return service.create_merge_review(db, context, body)


@router.post(
    "/people/merge-reviews/{review_id}/decision",
    response_model=MergeReviewResponse,
    operation_id="decideMergeReview",
)
def decide_merge_review(
    review_id: str, body: MergeDecisionRequest, db: DbDep, context: StaffContext
) -> MergeReviewResponse:
    return service.decide_merge_review(db, context, review_id, body)


# --- Membership lifecycle (§16/§19/§20/§21) and school-local data (§8/§9/§10) ---


@router.get(
    "/people/{person_id}/membership",
    response_model=MembershipResponse,
    operation_id="getMembership",
)
def get_membership(person_id: str, db: DbDep, context: StaffContext) -> MembershipResponse:
    return service.get_membership(db, context, person_id)


@router.patch(
    "/people/{person_id}/membership",
    response_model=MembershipResponse,
    operation_id="updateMemberData",
    responses={409: {"description": "Local member code already used in this org."}},
)
def update_member_data(
    person_id: str, body: UpdateMemberDataRequest, db: DbDep, context: StaffContext
) -> MembershipResponse:
    return service.update_member_data(db, context, person_id, body)


@router.post(
    "/people/{person_id}/membership/end",
    response_model=MembershipResponse,
    operation_id="endMembership",
    responses={409: {"description": "Already ended, or last owner of the school."}},
)
def end_membership(
    person_id: str, body: MembershipTransitionRequest, db: DbDep, context: StaffContext
) -> MembershipResponse:
    return service.end_membership(db, context, person_id, body)


@router.post(
    "/people/{person_id}/membership/suspend",
    response_model=MembershipResponse,
    operation_id="suspendMembership",
    responses={409: {"description": "Invalid transition, or last owner of the school."}},
)
def suspend_membership(
    person_id: str, body: MembershipTransitionRequest, db: DbDep, context: StaffContext
) -> MembershipResponse:
    return service.suspend_membership(db, context, person_id, body)


@router.post(
    "/people/{person_id}/membership/resume",
    response_model=MembershipResponse,
    operation_id="resumeMembership",
    responses={409: {"description": "Invalid transition for the current state."}},
)
def resume_membership(
    person_id: str, body: MembershipTransitionRequest, db: DbDep, context: StaffContext
) -> MembershipResponse:
    return service.resume_membership(db, context, person_id, body)


# --- Guardian management (§25 primary contact, §30 revoke access) ---


@router.get(
    "/people/{person_id}/guardians",
    response_model=list[GuardianContactResponse],
    operation_id="listGuardians",
)
def list_guardians(
    person_id: str, db: DbDep, context: StaffContext
) -> list[GuardianContactResponse]:
    return service.list_guardians(db, context, person_id)


@router.post(
    "/people/{person_id}/guardians/{guardian_person_id}/revoke",
    response_model=GuardianContactResponse,
    operation_id="revokeGuardianAccess",
)
def revoke_guardian_access(
    person_id: str,
    guardian_person_id: str,
    body: RevokeGuardianAccessRequest,
    db: DbDep,
    context: StaffContext,
) -> GuardianContactResponse:
    return service.revoke_guardian_access(db, context, person_id, guardian_person_id, body)


@router.post(
    "/people/{person_id}/guardians/{guardian_person_id}/primary",
    response_model=GuardianContactResponse,
    operation_id="setPrimaryContact",
)
def set_primary_contact(
    person_id: str, guardian_person_id: str, db: DbDep, context: StaffContext
) -> GuardianContactResponse:
    return service.set_primary_contact(db, context, person_id, guardian_person_id)


@router.get("/people/{person_id}", response_model=PersonResponse, operation_id="getPerson")
def get_person(person_id: str, db: DbDep, context: ContextDep) -> PersonResponse:
    return service.get_person(db, context, person_id)
