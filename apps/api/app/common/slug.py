"""Slugs for tenant discovery (the school "code" used at login)."""

from __future__ import annotations

import re

# Serbian-Latin diacritics fold to ASCII so codes are easy to type.
_TRANSLIT = str.maketrans(
    {
        "š": "s", "č": "c", "ć": "c", "ž": "z", "đ": "dj",
        "Š": "s", "Č": "c", "Ć": "c", "Ž": "z", "Đ": "dj",
    }
)


def slugify(text: str) -> str:
    folded = text.translate(_TRANSLIT).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    return cleaned or "skola"
