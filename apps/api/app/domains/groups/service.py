from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.domains.groups import repository
from app.domains.groups.enums import GroupCapacityMode
from app.domains.groups.models import Group, GroupMembership
from app.domains.groups.schemas import (
    CreateGroupRequest,
    GroupMemberResponse,
    GroupResponse,
)
from app.platform.audit.service import record_audit
from app.security.context import RequestContext


def create_group(db: Session, context: RequestContext, req: CreateGroupRequest) -> GroupResponse:
    group = Group(
        organization_id=context.organization_id,
        name=req.name.strip(),
        capacity_mode=req.capacity_mode,
        capacity=req.capacity,
    )
    db.add(group)
    db.commit()
    return GroupResponse.model_validate(group)


def list_groups(db: Session, context: RequestContext, params: PageParams) -> Page[GroupResponse]:
    groups, total = repository.list_org_groups(db, context.organization_id, params)
    return Page.build([GroupResponse.model_validate(g) for g in groups], total, params)


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
    return GroupMemberResponse(
        membership_id=membership.id, person_id=person.id, display_name=person.display_name
    )


def list_members(
    db: Session, context: RequestContext, group_id: str
) -> list[GroupMemberResponse]:
    group = repository.get_org_group(db, context.organization_id, group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")
    return [
        GroupMemberResponse(
            membership_id=m.id, person_id=p.id, display_name=p.display_name
        )
        for m, p in repository.list_members_with_people(db, group_id)
    ]
