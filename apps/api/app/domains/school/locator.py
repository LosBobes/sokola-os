"""Locator values: ``NormalizedSlug`` and ``SchoolCode`` (M04 §2.0, §3.7).

A locator points at a school. It does not prove anything about the person
holding it: §3.7.4 is explicit that a school code may help login discovery and
never grants membership, role or registration. That is why generation lives here
and authorization does not.
"""

from __future__ import annotations

import re
import secrets
import unicodedata

from app.common.errors import BadRequestError

# --- Slug ------------------------------------------------------------------

SLUG_MIN, SLUG_MAX = 3, 63
# Starts and ends alphanumeric, no consecutive hyphens: the lookahead after a
# hyphen is what forbids "a--b" without a second pass.
_SLUG = re.compile(
    rf"^[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){{{SLUG_MIN - 2},{SLUG_MAX - 2}}}[a-z0-9]$"
)

# --- School code -----------------------------------------------------------

#: Base32 without 0/O/1/I/L. The excluded characters are the ones people
#: transcribe wrongly when reading a code off a screen or a printed page, which
#: is the only way this value is ever entered.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 8
_CODE = re.compile(rf"^[{CODE_ALPHABET}]{{{CODE_LENGTH}}}$")

#: How the excluded characters are read when someone types them anyway.
_CODE_CONFUSIONS = str.maketrans({"0": "O", "O": "0", "1": "I", "I": "1", "L": "1"})


#: Đ/đ decompose to nothing useful under NFKD, so they are spelled out first.
_DJ: dict[int, str] = {ord("đ"): "dj", ord("Đ"): "Dj", ord("ð"): "dj"}


def normalize_slug(value: str) -> str:
    """Fold to the canonical slug form, or refuse.

    Serbian names carry diacritics that have no slug representation, so they are
    transliterated (``Škola Sokolić`` -> ``skola-sokolic``) rather than dropped,
    which would turn ``Šišić`` into ``ii``.
    """
    decomposed = unicodedata.normalize("NFKD", value.strip())
    spelled = decomposed.translate(_DJ)
    ascii_only = "".join(c for c in spelled if not unicodedata.combining(c))
    lowered = ascii_only.encode("ascii", "ignore").decode("ascii").lower()
    collapsed = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", lowered)).strip("-")

    if not _SLUG.match(collapsed):
        raise BadRequestError(
            "Adresa škole mora imati 3–63 znaka: mala slova, cifre i crtice između njih."
        )
    return collapsed


def is_valid_slug(value: str) -> bool:
    return bool(_SLUG.match(value))


def generate_school_code() -> str:
    """A fresh, uniformly random code.

    Not derived from the school's name, id or creation order: a code that
    encodes anything about the school lets someone enumerate schools from one
    example, and the whole point of §3.7 is that a locator is a pointer, not a
    secret *and* not a census.
    """
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_school_code(value: str) -> str:
    """Uppercase, strip separators, and map the characters people confuse.

    Someone reading a code aloud will say "oh" for ``0`` and "ell" for ``1``.
    The alphabet excludes the ambiguous glyphs precisely so this mapping is
    unambiguous in one direction, which makes a mistyped code resolve instead of
    returning a safe-not-found the user cannot act on.
    """
    cleaned = re.sub(r"[\s_-]", "", value.strip().upper()).translate(_CODE_CONFUSIONS)
    if not _CODE.match(cleaned):
        raise BadRequestError("Šifra škole ima tačno 8 znakova (slova i cifre).")
    return cleaned


def is_valid_school_code(value: str) -> bool:
    return bool(_CODE.match(value))
