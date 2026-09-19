"""Unified operational search (PRD 15), one box that fans out over people,
groups, sessions, events, and charges instead of five separately-scoped lists.

No ``service.py``: this domain is read-only and has nothing to orchestrate
beyond the fan-out itself, so the endpoint calls ``repository`` directly and
shapes the response, the same "router + repository only" shape as other
read-heavy, cross-cutting surfaces in this codebase.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.domains.search import repository
from app.domains.search.enums import SearchResultType
from app.domains.search.schemas import SearchResponse, SearchResultItem
from app.security.deps import ContextDep, DbDep

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse, operation_id="search")
def search(
    db: DbDep, context: ContextDep, q: Annotated[str, Query()] = ""
) -> SearchResponse:
    """Search is gated on ``ContextDep`` alone, no new permission area. It only
    ever surfaces rows each sub-query already re-scopes to ``context.
    school_id`` the same way that domain's own list endpoint would (e.g.
    ``GET /charges`` is likewise ``ContextDep``-only today, with no per-area
    guard), so this is behaviour-consistent with the codebase, not a new
    exposure. A future permission area is easy to add here if that changes.
    """
    term = q.strip()
    if not term:
        return SearchResponse(query=term, results=[])

    org_id = context.school_id
    results: list[SearchResultItem] = []

    for person, local_code in repository.search_people(db, org_id, term):
        results.append(
            SearchResultItem(
                type=SearchResultType.PERSON,
                id=person.id,
                title=person.display_name,
                subtitle=local_code or "Član organizacije",
            )
        )

    for group in repository.search_groups(db, org_id, term):
        subtitle = (
            f"Grupa · kapacitet {group.capacity}"
            if group.capacity is not None
            else "Grupa"
        )
        results.append(
            SearchResultItem(
                type=SearchResultType.GROUP, id=group.id, title=group.name, subtitle=subtitle
            )
        )

    for session, group in repository.search_sessions(db, org_id, term):
        title = session.title or f"Trening · {group.name}"
        results.append(
            SearchResultItem(
                type=SearchResultType.SESSION,
                id=session.id,
                title=title,
                subtitle=f"{group.name} · {session.starts_at:%d.%m.%Y %H:%M}",
            )
        )

    for event in repository.search_events(db, org_id, term):
        results.append(
            SearchResultItem(
                type=SearchResultType.EVENT,
                id=event.id,
                title=event.title,
                subtitle=f"Događaj · {event.starts_at:%d.%m.%Y %H:%M}",
            )
        )

    for charge, person in repository.search_charges(db, org_id, term):
        amount = charge.amount_due / 100
        results.append(
            SearchResultItem(
                type=SearchResultType.CHARGE,
                id=charge.id,
                title=charge.description,
                subtitle=f"{person.display_name} · {amount:.2f} {charge.currency}",
            )
        )

    return SearchResponse(query=term, results=results)
