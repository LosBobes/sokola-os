"""TEN-Q01 `ListMyAvailableTenantContexts` (M03 §12, §5.4, §6.4).

"Which schools may I work in, and as what?" — the question behind the X03
chooser, asked once when a person has more than one school.

Like TEN-Q02 this lives in the application layer, because answering it needs
three domains at once: M03's school and security state, M06's membership
evidence, and M05's role definitions for the workspace mapping. §12 names that
arrangement and adds the constraint that matters — it must combine them
"bez stvaranja M03→M05 domain zavisnosti".

What it must not return is as load-bearing as what it must. §5.4: no finances,
no debt, no attendance, no documents, no message content, no member counts, no
other people's schools, and no reason for a security restriction. A chooser
that leaked any of those would be handing out tenant data *before* a tenant
context exists.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.errors import BadRequestError
from app.domains.authorization.enums import DOMAIN_SCHOOL, PolicyRevisionStatus
from app.domains.authorization.models import (
    AuthorizationPolicyRevision,
    RoleDefinition,
)
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode
from app.domains.identity.models import RoleAssignment
from app.domains.school.enums import MembershipStatus, SchoolStatus
from app.domains.school.models import School, SchoolMembership
from app.domains.tenancy.enums import SchoolMode
from app.domains.tenancy.models import TenantContextUsage

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

#: This repo's `RoleCode` against M05 §2.4's canonical role keys.
#:
#: Only the *workspace* mapping, and only because that part is settled while
#: the permission mapping is not (F-29). The ambiguity there is `ADMIN`: it
#: could become `MANAGER` or `LIMITED_ADMIN`, and those differ sharply in what
#: they may do. They do not differ here — §2.4 puts `OWNER`, `MANAGER` and
#: `LIMITED_ADMIN` all in the `ADMIN` workspace — so a chooser can be built on
#: this today without pre-deciding F-29.
#:
#: `STUDENT` is absent on purpose. M05 has no student role, so there is no
#: workspace to offer, and inventing one would be exactly the guess F-29 is
#: open to avoid. A student-only account sees an empty list, which §12 calls a
#: successful neutral result.
_WORKSPACE_ROLE_KEY: dict[RoleCode, str] = {
    RoleCode.OWNER: "OWNER",
    RoleCode.MANAGER: "MANAGER",
    # Both candidate resolutions of F-29 land in the ADMIN workspace.
    RoleCode.ADMIN: "MANAGER",
    RoleCode.TRAINER: "INSTRUCTOR",
    RoleCode.PARENT: "GUARDIAN",
}


@dataclasses.dataclass(frozen=True, slots=True)
class WorkspaceOption:
    """§5.4. One display choice inside one school."""

    workspace_key: str
    display_order: int


@dataclasses.dataclass(frozen=True, slots=True)
class AvailableTenantContext:
    """§5.4's query model. A query model, not a table."""

    school_id: str
    school_display_name: str
    school_mode: SchoolMode
    workspace_options: tuple[WorkspaceOption, ...]
    last_used_workspace_key: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class AvailableContextPage:
    items: tuple[AvailableTenantContext, ...]
    next_cursor: str | None


def _normalize(name: str) -> str:
    """§12's "normalizovani naziv škole" for sorting.

    Case- and accent-folded, so "Ćuprija" and "Cuprija" sort together rather
    than landing wherever the database collation happens to put them. The sort
    has to be stable across deployments, and a collation is not.
    """
    folded = unicodedata.normalize("NFKD", name.casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _encode_cursor(sort_key: tuple[str, str, str]) -> str:
    """An opaque cursor over the full sort key.

    Opaque because §5.4 keeps a chooser free of anything a client could read
    into: a cursor spelling out a school id and a timestamp would be a small
    leak of exactly the shape the section forbids. Encoding the *whole* key,
    not just the id, is what makes paging stable — the key is unique, so
    "everything after this" has one answer.
    """
    raw = "\x1f".join(sort_key).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str, str]:
    padding = "=" * (-len(cursor) % 4)
    try:
        parts = base64.urlsafe_b64decode(cursor + padding).decode("utf-8").split("\x1f")
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise BadRequestError("Neispravan cursor.") from exc
    if len(parts) != 3:
        raise BadRequestError("Neispravan cursor.")
    return parts[0], parts[1], parts[2]


def list_available_contexts(
    db: Session,
    *,
    person_id: str,
    user_account_id: str,
    cursor: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> AvailableContextPage:
    """§12's TEN-Q01.

    One item per school, never one per role: §6.4 is explicit that the same
    person holding two roles in one school gets *one* tenant context with two
    workspace options. Building this off role assignments directly would
    produce a duplicate school per role, which is the bug the section names.
    """
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise BadRequestError(f"page_size mora biti između 1 i {MAX_PAGE_SIZE}.")

    revision_id = db.execute(
        select(AuthorizationPolicyRevision.id).where(
            AuthorizationPolicyRevision.status == PolicyRevisionStatus.ACTIVE
        )
    ).scalar_one_or_none()
    if revision_id is None:
        # Fail closed. §3.1: an unavailable policy store is a deny, not an
        # empty answer that looks like "you belong nowhere".
        raise BadRequestError("Autorizaciona politika trenutno nije dostupna.")

    workspace_of = {
        row.role_key: row
        for row in db.execute(
            select(RoleDefinition).where(
                RoleDefinition.policy_revision_id == revision_id,
                RoleDefinition.authorization_domain_key == DOMAIN_SCHOOL,
            )
        ).scalars()
    }

    # §6.1: an allowed school needs *both* current ACTIVE membership evidence
    # and an active role assignment. A role without membership is not access —
    # that is the step §8 adds, and a chooser that skipped it would offer a
    # school the request guard then refuses.
    rows = db.execute(
        select(School, RoleAssignment.role_code)
        .join(
            SchoolMembership,
            (SchoolMembership.school_id == School.id)
            & (SchoolMembership.person_id == person_id)
            & (SchoolMembership.status == MembershipStatus.ACTIVE)
            & (SchoolMembership.record_status == RecordStatus.ACTIVE),
        )
        .join(
            RoleAssignment,
            (RoleAssignment.school_id == School.id)
            & (RoleAssignment.person_id == person_id)
            & (RoleAssignment.status == RoleAssignmentStatus.ACTIVE),
        )
        .where(School.status != SchoolStatus.DEACTIVATED)
    ).all()

    usage = {
        row.school_id: row
        for row in db.execute(
            select(TenantContextUsage).where(
                TenantContextUsage.user_account_id == user_account_id
            )
        ).scalars()
    }

    grouped: dict[str, tuple[School, set[str]]] = {}
    for school, role_code in rows:
        role_key = _WORKSPACE_ROLE_KEY.get(role_code)
        definition = workspace_of.get(role_key) if role_key else None
        if definition is None or definition.workspace_key is None:
            # A role this revision has no workspace for offers nothing. Not an
            # error: it is how STUDENT, and any role a future revision retires,
            # simply stops appearing.
            continue
        _, keys = grouped.setdefault(school.id, (school, set()))
        keys.add(definition.workspace_key)

    items: list[tuple[tuple[str, str, str], AvailableTenantContext]] = []
    for school_id, (school, keys) in grouped.items():
        options = tuple(
            sorted(
                (
                    WorkspaceOption(
                        workspace_key=key,
                        display_order=min(
                            d.display_order
                            for d in workspace_of.values()
                            if d.workspace_key == key
                        ),
                    )
                    for key in keys
                ),
                # §12: stable display order, then the key itself as the
                # tie-break — two roles can share a workspace and therefore an
                # order, and a sort that stopped at the order would not be
                # deterministic.
                key=lambda o: (o.display_order, o.workspace_key),
            )
        )
        seen = usage.get(school_id)
        # §12's sort key. Descending on last use is expressed by inverting the
        # timestamp here rather than by sorting twice: a school never visited
        # sorts after every school that has been, and "" is less than any
        # inverted timestamp.
        last_used = seen.last_used_at.isoformat() if seen is not None else ""
        items.append(
            (
                (_invert(last_used), _normalize(school.name), school.id),
                AvailableTenantContext(
                    school_id=school.id,
                    school_display_name=school.name,
                    school_mode=(
                        SchoolMode.REGULAR
                        if school.status is SchoolStatus.ACTIVE
                        else SchoolMode.SETUP_ONLY
                    ),
                    workspace_options=options,
                    last_used_workspace_key=(
                        seen.last_workspace_key if seen is not None else None
                    ),
                ),
            )
        )

    items.sort(key=lambda pair: pair[0])
    if cursor is not None:
        after = _decode_cursor(cursor)
        items = [pair for pair in items if pair[0] > after]

    page = items[:page_size]
    next_cursor = _encode_cursor(page[-1][0]) if len(items) > page_size else None
    return AvailableContextPage(
        items=tuple(entry for _, entry in page), next_cursor=next_cursor
    )


def _invert(timestamp: str) -> str:
    """Turn "most recent first" into a plain ascending sort.

    An ISO timestamp sorts lexicographically, so complementing each digit makes
    later times sort earlier. Doing it in the key keeps one comparison for the
    whole tuple — mixing a descending field with two ascending ones otherwise
    needs either two passes or a custom comparator, and both are easier to get
    subtly wrong than this is.
    """
    if not timestamp:
        # Never used: sorts last, because every inverted timestamp is non-empty
        # and starts with a digit-complement character above the empty string.
        return "~"
    return "".join(chr(ord("9") - int(c)) if c.isdigit() else c for c in timestamp)
