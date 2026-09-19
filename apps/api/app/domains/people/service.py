from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import BadRequestError, ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.domains.identity.enums import PersonIdentityStatus
from app.domains.identity.models import Person
from app.domains.people import membership as membership_service
from app.domains.people import profile_models, repository
from app.domains.people.enums import GuardianAccessStatus, GuardianRelationshipType
from app.domains.people.models import GuardianRelationship, GuardianSchoolAccess
from app.domains.people.schemas import (
    CreatePersonRequest,
    GuardianContactResponse,
    MembershipResponse,
    MembershipTransitionRequest,
    PersonResponse,
    PersonSummary,
    RevokeGuardianAccessRequest,
    UpdateMemberDataRequest,
)
from app.domains.school.enums import MembershipStatus, MembershipType
from app.domains.school.models import SchoolMembership
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
        db, context.school_id, req.given_name, req.family_name
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
        SchoolMembership(
            school_id=context.school_id,
            person_id=person.id,
            membership_type=req.member_type,
        )
    )

    repository.get_or_create_profile(db, context.school_id, person.id)

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
        school_id=context.school_id,
        actor_person_id=context.person_id,
        context={"duplicate_override": req.allow_possible_duplicate},
    )
    enqueue(
        db,
        event_type="person.created",
        payload={"person_id": person.id, "school_id": context.school_id},
        school_id=context.school_id,
    )
    db.commit()
    return PersonResponse.model_validate(person)


def list_people(
    db: Session,
    context: RequestContext,
    params: PageParams,
    *,
    member_type: MembershipType | None = None,
) -> Page[PersonSummary]:
    rows, total = repository.list_school_people(
        db, context.school_id, params, member_type=member_type
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
    person = repository.get_school_person(db, context.school_id, person_id)
    if person is None:
        raise NotFoundError("Osoba nije pronađena.")
    return PersonResponse.model_validate(person)


# ---------------------------------------------------------------------------
# Membership lifecycle (§16/§19/§20/§21), end / suspend / resume
# ---------------------------------------------------------------------------


def _load_member(
    db: Session, context: RequestContext, person_id: str
) -> tuple[SchoolMembership, Person]:
    membership = repository.get_membership(db, context.school_id, person_id)
    person = repository.get_school_person(db, context.school_id, person_id)
    if membership is None or person is None:
        # Foreign or nonexistent resource returns the same error, never leak.
        raise NotFoundError("Osoba nije pronađena.")
    return membership, person


def _guard_not_last_owner(db: Session, school_id: str, person_id: str) -> None:
    """§22, never strip the school of its last remaining active owner."""
    if (
        repository.is_active_owner(db, school_id, person_id)
        and repository.count_active_owners(db, school_id) <= 1
    ):
        raise ConflictError(_LAST_OWNER_ERROR)


def _emit_membership_change(
    db: Session,
    context: RequestContext,
    membership: SchoolMembership,
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
        entity_type="school_membership",
        entity_id=membership.id,
        summary=summary,
        school_id=context.school_id,
        actor_person_id=context.person_id,
        context={"person_id": person.id},
    )
    enqueue(
        db,
        event_type=f"membership.{action}",
        payload={
            "membership_id": membership.id,
            "person_id": person.id,
            "school_id": context.school_id,
        },
        school_id=context.school_id,
    )


def get_membership(
    db: Session, context: RequestContext, person_id: str
) -> MembershipResponse:
    membership, _ = _load_member(db, context, person_id)
    return _membership_response(db, context.school_id, membership)


def _membership_response(
    db: Session, school_id: str, membership: SchoolMembership
) -> MembershipResponse:
    """Compose the wire shape from the two rows it now spans.

    The API keeps ``member_type``, ``local_member_code`` and ``admin_note``:
    those names are the existing public contract, and M06 does not dictate an
    API shape. Only the storage moved — the code and note describe the person as
    this school files them (§2.4), not one of their memberships.
    """
    profile = repository.get_or_create_profile(db, school_id, membership.person_id)
    return MembershipResponse(
        id=membership.id,
        person_id=membership.person_id,
        status=membership.status,
        member_type=membership.membership_type,
        local_member_code=profile.local_person_code,
        admin_note=profile.administrative_note,
    )


def _reason_code(reason: str | None, fallback: str) -> str:
    """A closed-registry code for the transition, derived from the free-text
    reason the current API accepts.

    M06 §2.3 wants a code; this endpoint predates that and takes prose. Rather
    than invent a mapping that would read as authoritative, the prose is kept
    in the audit entry and the code records only *which command* ran — which is
    true, and is replaced by a real registry when the MEM commands get their own
    surface.
    """
    return fallback


def end_membership(
    db: Session, context: RequestContext, person_id: str, req: MembershipTransitionRequest
) -> MembershipResponse:
    membership, person = _load_member(db, context, person_id)
    if membership.status is MembershipStatus.TERMINATED:
        raise ConflictError("Članstvo je već okončano.")
    # §3.9: the owner invariant is checked before the M06 transition, by the
    # use-case that owns both — M06 must not reach into M05 itself.
    _guard_not_last_owner(db, context.school_id, person_id)
    membership_service.terminate_membership(
        db, membership, reason_code=_reason_code(req.reason, "MEMBERSHIP_ENDED")
    )
    _emit_membership_change(db, context, membership, person, "ended", req.reason)
    db.commit()
    return _membership_response(db, context.school_id, membership)


def suspend_membership(
    db: Session, context: RequestContext, person_id: str, req: MembershipTransitionRequest
) -> MembershipResponse:
    membership, person = _load_member(db, context, person_id)
    if membership.status is MembershipStatus.TERMINATED:
        raise ConflictError("Okončano članstvo ne može biti suspendovano.")
    if membership.status is MembershipStatus.SUSPENDED:
        raise ConflictError("Članstvo je već suspendovano.")
    _guard_not_last_owner(db, context.school_id, person_id)
    membership_service.suspend_membership(
        db, membership, reason_code=_reason_code(req.reason, "MEMBERSHIP_SUSPENDED")
    )
    _emit_membership_change(db, context, membership, person, "suspended", req.reason)
    db.commit()
    return _membership_response(db, context.school_id, membership)


def resume_membership(
    db: Session, context: RequestContext, person_id: str, req: MembershipTransitionRequest
) -> MembershipResponse:
    membership, person = _load_member(db, context, person_id)
    if membership.status is MembershipStatus.ACTIVE:
        raise ConflictError("Članstvo je već aktivno.")
    if membership.status is MembershipStatus.TERMINATED:
        # Ended is terminal; reactivation is a new membership, never a revived row.
        raise ConflictError("Okončano članstvo se ne može nastaviti.")
    membership_service.activate_membership(db, membership)
    _emit_membership_change(db, context, membership, person, "resumed", req.reason)
    db.commit()
    return _membership_response(db, context.school_id, membership)


# ---------------------------------------------------------------------------
# School-local member data (§8/§9/§10), local code + admin note
# ---------------------------------------------------------------------------


def update_member_data(
    db: Session, context: RequestContext, person_id: str, req: UpdateMemberDataRequest
) -> MembershipResponse:
    membership, person = _load_member(db, context, person_id)
    fields = req.model_fields_set

    # The school-local code and note describe the *person* as this school files
    # them, not one of their memberships (§2.4), so they live on the profile.
    profile = repository.get_or_create_profile(db, context.school_id, person_id)

    if "local_member_code" in fields:
        raw = (req.local_member_code or "").strip() or None
        if raw is None:
            profile.local_person_code = None
            profile.normalized_local_person_code = None
        else:
            try:
                normalized = profile_models.normalize_local_person_code(raw)
            except ValueError as exc:
                raise BadRequestError("Lokalna šifra člana nije u ispravnom obliku.") from exc
            if (
                repository.find_local_code_owner(db, context.school_id, raw, person_id)
                is not None
            ):
                raise ConflictError("Lokalna šifra člana se već koristi u ovoj školi.")
            profile.local_person_code = raw
            profile.normalized_local_person_code = normalized
        profile.version += 1

    if "admin_note" in fields:
        profile.administrative_note = (req.admin_note or "").strip() or None
        profile.version += 1

    if "member_type" in fields and req.member_type is not None:
        membership.membership_type = req.member_type

    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="membership.data_updated",
        entity_type="school_membership",
        entity_id=membership.id,
        summary=f"Ažurirani lokalni podaci člana za „{person.display_name}“.",
        school_id=context.school_id,
        actor_person_id=context.person_id,
        context={"person_id": person.id},
    )
    db.commit()
    return _membership_response(db, context.school_id, membership)


# ---------------------------------------------------------------------------
# Guardian management (§25 primary contact, §30 revoke access)
# ---------------------------------------------------------------------------


def _relationship_type(
    db: Session, access: GuardianSchoolAccess
) -> GuardianRelationshipType:
    rel = db.execute(
        select(GuardianRelationship).where(
            GuardianRelationship.guardian_person_id == access.guardian_person_id,
            GuardianRelationship.child_person_id == access.child_person_id,
        )
    ).scalar_one_or_none()
    return rel.relationship_type if rel is not None else GuardianRelationshipType.OTHER


def _contact_response(
    db: Session, access: GuardianSchoolAccess, guardian: Person
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
    child = repository.get_school_person(db, context.school_id, person_id)
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
            db, context.school_id, person_id
        )
    ]


def revoke_guardian_access(
    db: Session,
    context: RequestContext,
    person_id: str,
    guardian_person_id: str,
    req: RevokeGuardianAccessRequest,
) -> GuardianContactResponse:
    child = repository.get_school_person(db, context.school_id, person_id)
    if child is None:
        raise NotFoundError("Osoba nije pronađena.")
    access = repository.get_guardian_access(
        db, context.school_id, person_id, guardian_person_id
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
        entity_type="guardian_school_access",
        entity_id=access.id,
        summary=summary,
        school_id=context.school_id,
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
            "school_id": context.school_id,
        },
        school_id=context.school_id,
    )
    db.commit()
    return _contact_response(db, access, guardian)


def set_primary_contact(
    db: Session, context: RequestContext, person_id: str, guardian_person_id: str
) -> GuardianContactResponse:
    child = repository.get_school_person(db, context.school_id, person_id)
    if child is None:
        raise NotFoundError("Osoba nije pronađena.")
    access = repository.get_guardian_access(
        db, context.school_id, person_id, guardian_person_id
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
    for current in repository.child_primary_contacts(db, context.school_id, person_id):
        current.is_primary_contact = False
    db.flush()
    access.is_primary_contact = True

    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="guardian.primary_set",
        entity_type="guardian_school_access",
        entity_id=access.id,
        summary=(
            f"„{guardian.display_name}“ je označen/a kao primarni kontakt za "
            f"„{child.display_name}“."
        ),
        school_id=context.school_id,
        actor_person_id=context.person_id,
        context={"guardian_person_id": guardian_person_id, "child_person_id": person_id},
    )
    db.commit()
    return _contact_response(db, access, guardian)
