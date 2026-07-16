"""Prefixed, lexicographically sortable identifiers.

IDs are ``<prefix>_<ulid>`` (e.g. ``per_01J...``). The ULID component is
time-sortable, which keeps index locality good and makes IDs debuggable without
leaking sequential counts.
"""

from __future__ import annotations

from ulid import ULID


def new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"
