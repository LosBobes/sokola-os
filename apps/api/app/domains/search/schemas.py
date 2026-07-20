from __future__ import annotations

from pydantic import BaseModel

from app.domains.search.enums import SearchResultType


class SearchResultItem(BaseModel):
    """One matched row, already shaped for a result list: enough to render and
    to navigate to the underlying record without a follow-up lookup."""

    type: SearchResultType
    id: str
    title: str
    subtitle: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
