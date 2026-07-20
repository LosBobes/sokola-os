from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.domains.groups import repository
from app.domains.groups.enums import GroupCapacityMode, GroupMembershipStatus
from app.domains.groups.models import Group, GroupMembership
from app.domains.groups.schemas import (
    CreateGroupRequest,
    EndGroupMembershipRequest,
    GroupMemberResponse,
    GroupMembershipTransitionRequest,
    GroupResponse,
    SetMembershipDiscountRequest,
    UpdateGroupRequest,
)
from app.domains.identity.models import Person
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def _group_response(group: Group) -> GroupResponse:
    return GroupResponse.model_validate(group)


def _member_response(membership: GroupMembership, person: Person) -> GroupMemberResponse:
    return GroupMemberResponse(
        membership_id=membership.id,
        person_id=person.id,
        display_name=person.display_name,
        status=membership.status,
        discount_minor=membership.discount_minor,
        joined_at=membership.joined_at,
        ended_at=membership.ended_at,
        end_reason=membership.end_reason,
    )


def _resolve_program(db: Session, context: RequestContext, program_id: str | None) -> str | None:
    if program_id is None:
        return None
    program = repository.get_org_program(db, context.organization_id, program_id)
    if program is None:
        raise NotFoundError("Program nije pronađen.")
    return program.id


def _resolve_location(
    db: Session, context: RequestContext, location_id: str | None
) -> str | None:
    if location_id is None:
        return None
    location = repository.get_org_location(db, context.organization_id, location_id)
    if location is None:
        raise NotFoundError("Ogranak nije pronađen.")
    return location.id


def create_group(db: Session, context: RequestContext, req: CreateGroupRequest) -> GroupResponse:
    program_id = _resolve_program(db, context, req.program_id)
    location_id = _resolve_location(db, context, req.location_id)
    group = Group(
        organization_id=context.organization_id,
        name=req.name.strip(),
        capacity_mode=req.capacity_mode,
        capacity=req.capacity,
        program_id=program_id,
        location_id=location_id,
        base_monthly_price_minor=req.base_monthly_price_minor,
    )
    db.add(group)
    db.commit()
    return _group_response(group)


def list_groups(db: Session, context: RequestContext, params: PageParams) -> Page[GroupResponse]:
    groups, total = repository.list_org_groups(db, context.organization_id, params)
    return Page.build([_group_response(g) for g in groups], total, params)


def update_group(
    db: Session, context: RequestContext, group_id: str, req: UpdateGroupRequest
) -> GroupResponse:
    """M1/M4: sets the group's list price and/or its structure links. Partial —
    only fields present in the request are touched (see UpdateGroupRequest)."""
    group = repository.get_org_group(db, context.organization_id, group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")

    fields = req.model_fields_set
    if "program_id" in fields:
        group.program_id = _resolve_program(db, context, req.program_id)
    if "location_id" in fields:
        group.location_id = _resolve_location(db, context, req.location_id)
    if "base_monthly_price_minor" in fields:
        group.base_monthly_price_minor = req.base_monthly_price_minor

    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="group.updated",
        entity_type="group",
        entity_id=group.id,
        summary=f"Izmenjena grupa „{group.name}“.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    db.commit()
    return _group_response(group)


def add_member(
    db: Session, context: RequestContext, group_id: str, person_id: str
) -> GroupMemberResponse:
    group = repository.get_org_group(db, context.organization_id, group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")

    # The person must be a visible member of THIS organization.
    person = repository.get_member_person(db, context.organization_id, person_id)
    if person is None:
        raise NotFoundError("Osoba nije pronađena u ovoj školi.")

    if repository.get_active_membership(db, group_id, person_id) is not None:
        raise ConflictError("Osoba je već član ove grupe.")

    if (
        group.capacity_mode is GroupCapacityMode.LIMITED
        and group.capacity is not None
        and repository.count_active_members(db, group_id) >= group.capacity
    ):
        raise ConflictError("Grupa je popunjena.")

    membership = GroupMembership(
        group_id=group_id,
        organization_id=context.organization_id,
        person_id=person_id,
        joined_at=dt.datetime.now(tz=dt.UTC),
    )
    db.add(membership)
    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="group.member_added",
        entity_type="group",
        entity_id=group_id,
        summary=f"„{person.display_name}“ dodat/a u grupu „{group.name}“.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    db.commit()
    return _member_response(membership, person)


def list_members(
    db: Session, context: RequestContext, group_id: str
) -> list[GroupMemberResponse]:
    group = repository.get_org_group(db, context.organization_id, group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")
    return [
        _member_response(m, p) for m, p in repository.list_members_with_people(db, group_id)
    ]


# ---------------------------------------------------------------------------
# Membership lifecycle (PRD 04 M2) — suspend / resume / end
# ---------------------------------------------------------------------------


def _load_group_membership(
    db: Session, context: RequestContext, group_id: str, membership_id: str
) -> tuple[Group, GroupMembership, Person]:
    group = repository.get_org_group(db, context.organization_id, group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")
    found = repository.get_org_membership(db, context.organization_id, group_id, membership_id)
    if found is None:
        # Foreign or nonexistent membership id returns the same error — never leak.
        raise NotFoundError("Član grupe nije pronađen.")
    membership, person = found
    return group, membership, person


def _emit_membership_change(
    db: Session,
    context: RequestContext,
    group: Group,
    membership: GroupMembership,
    person: Person,
    action: str,
    reason: str | None,
) -> None:
    verb = {"ended": "okončano", "suspended": "suspendovano", "resumed": "nastavljeno"}[action]
    summary = f"Članstvo za „{person.display_name}“ u grupi „{group.name}“ je {verb}."
    if reason and reason.strip():
        summary += f" Razlog: {reason.strip()}"
    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action=f"group_membership.{action}",
        entity_type="group_membership",
        entity_id=membership.id,
        summary=summary,
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"group_id": group.id, "person_id": person.id},
    )
    enqueue(
        db,
        event_type=f"group_membership.{action}",
        payload={
            "membership_id": membership.id,
            "group_id": group.id,
            "person_id": person.id,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )


def suspend_membership(
    db: Session,
    context: RequestContext,
    group_id: str,
    membership_id: str,
    req: GroupMembershipTransitionRequest,
) -> GroupMemberResponse:
    group, membership, person = _load_group_membership(db, context, group_id, membership_id)
    if membership.status is GroupMembershipStatus.ENDED:
        raise ConflictError("Okončano članstvo ne može biti suspendovano.")
    if membership.status is GroupMembershipStatus.SUSPENDED:
        raise ConflictError("Članstvo je već suspendovano.")
    membership.status = GroupMembershipStatus.SUSPENDED
    _emit_membership_change(db, context, group, membership, person, "suspended", req.reason)
    db.commit()
    return _member_response(membership, person)


def resume_membership(
    db: Session,
    context: RequestContext,
    group_id: str,
    membership_id: str,
    req: GroupMembershipTransitionRequest,
) -> GroupMemberResponse:
    group, membership, person = _load_group_membership(db, context, group_id, membership_id)
    if membership.status is GroupMembershipStatus.ENDED:
        # Ended is terminal; reactivation is a new membership, never a revived row.
        raise ConflictError("Okončano članstvo se ne može nastaviti.")
    if membership.status is GroupMembershipStatus.ACTIVE:
        raise ConflictError("Članstvo je već aktivno.")
    membership.status = GroupMembershipStatus.ACTIVE
    _emit_membership_change(db, context, group, membership, person, "resumed", req.reason)
    db.commit()
    return _member_response(membership, person)


def end_membership(
    db: Session,
    context: RequestContext,
    group_id: str,
    membership_id: str,
    req: EndGroupMembershipRequest,
) -> GroupMemberResponse:
    group, membership, person = _load_group_membership(db, context, group_id, membership_id)
    if membership.status is GroupMembershipStatus.ENDED:
        raise ConflictError("Članstvo je već okončano.")
    membership.status = GroupMembershipStatus.ENDED
    membership.ended_at = dt.datetime.now(tz=dt.UTC)
    membership.end_reason = req.end_reason
    _emit_membership_change(db, context, group, membership, person, "ended", req.reason)
    db.commit()
    return _member_response(membership, person)


# ---------------------------------------------------------------------------
# Per-member discount (PRD 04 M1)
# ---------------------------------------------------------------------------


def set_membership_discount(
    db: Session,
    context: RequestContext,
    group_id: str,
    membership_id: str,
    req: SetMembershipDiscountRequest,
) -> GroupMemberResponse:
    group, membership, person = _load_group_membership(db, context, group_id, membership_id)
    membership.discount_minor = req.discount_minor
    record_audit(
        db,
        data_class=AuditDataClass.FINANCIAL,
        action="group_membership.discount_updated",
        entity_type="group_membership",
        entity_id=membership.id,
        summary=(
            f"Popust za „{person.display_name}“ u grupi „{group.name}“ "
            f"postavljen na {req.discount_minor}."
        ),
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"group_id": group.id, "person_id": person.id},
    )
    db.commit()
    return _member_response(membership, person)
