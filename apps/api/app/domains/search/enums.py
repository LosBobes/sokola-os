from __future__ import annotations

import enum


class SearchResultType(enum.StrEnum):
    """Which entity a search result came from — drives icon/link choice client-side."""

    PERSON = "PERSON"
    GROUP = "GROUP"
    SESSION = "SESSION"
    EVENT = "EVENT"
    CHARGE = "CHARGE"
