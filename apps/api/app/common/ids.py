"""Prefixed, lexicographically sortable identifiers.

IDs are ``<prefix>_<ulid>`` (e.g. ``per_01J...``). The ULID component is
time-sortable, which keeps index locality good and makes IDs debuggable without
leaking sequential counts.
"""

from __future__ import annotations

import secrets

from ulid import ULID


def new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def new_random_id(prefix: str) -> str:
    """A prefixed identifier with no time component.

    ``new_id`` is ULID-based and therefore time-sortable, which is good for
    index locality and bad wherever an id must be *unpredictable* — a ULID
    leaks when it was minted and narrows a guess to its random half. M01 §3.1
    and §3.2 ask for unpredictable ids on the account and the session, so those
    use this instead and give up the sort locality.
    """
    return f"{prefix}_{secrets.token_urlsafe(24)}"
