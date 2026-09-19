"""`SchoolPersonProfile` (M06 §2.4): what one school records about one person.

This is the row that makes a global :class:`~app.domains.identity.models.Person`
*visible inside one tenant*, and it is where school-local facts live — the code
the school files them under, an administrative note — so that none of it is
carried between schools on the global identity.

One profile per ``(school_id, person_id)``, regardless of how many membership
types that person holds there: a school knows a person once, even when they are
simultaneously a parent and a coach.

It also supplies the tenant-safe reference other modules need. M04 §2.6 requires
an owner nomination to point at ``(school_id, id, person_id)`` here, which is why
:attr:`SchoolPersonProfile` carries a unique on exactly that triple — see finding
F-14, which this closes.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.ids import new_id

#: Control, BiDi, zero-width and soft-hyphen characters. §2.4 excludes them
#: because they are invisible: two codes that look identical on screen but
#: differ by a zero-width joiner would both be accepted, and the school would
#: have two records it cannot tell apart.
_INVISIBLE = re.compile(
    "[\u0000-\u001f\u007f­​-‏ -‮⁠-⁤⁪-⁯﻿]"
)


def normalize_local_person_code(value: str) -> str:
    """NFKC plus an outer trim, and deliberately **no** casefold (§2.4).

    Case is preserved because M20's external-reference contract is
    case-sensitive: folding here would quietly merge ``AB-1`` and ``ab-1``,
    which an import treats as two different pupils.
    """
    normalized = unicodedata.normalize("NFKC", value).strip()
    if _INVISIBLE.search(normalized):
        raise ValueError("local person code contains invisible characters")
    if not 1 <= len(normalized) <= 64:
        raise ValueError("local person code must be 1..64 characters")
    return normalized


class SchoolPersonProfile(Base, TimestampMixin):
    """§2.4. One school's view of one person."""

    __tablename__ = "school_person_profile"
    __table_args__ = (
        UniqueConstraint("school_id", "person_id", name="uq_school_person_profile"),
        # The tenant-safe reference other modules foreign-key against. Adds no
        # uniqueness — `id` is already the primary key — but lets a reference
        # name the tenant and the person as part of itself, so a row in another
        # school cannot be pointed at at all.
        UniqueConstraint(
            "school_id", "id", "person_id", name="uq_school_person_profile_tenant_person"
        ),
        # Unique within the school when set. Partial, because most people have
        # no school-local code and NULLs must not collide.
        Index(
            "uq_school_person_profile_code",
            "school_id",
            "normalized_local_person_code",
            unique=True,
            postgresql_where=text("normalized_local_person_code IS NOT NULL"),
        ),
        CheckConstraint(
            "(local_person_code IS NULL) = (normalized_local_person_code IS NULL)",
            name="ck_school_person_profile_code_pair",
        ),
        CheckConstraint(
            "administrative_note IS NULL OR length(administrative_note) <= 500",
            name="ck_school_person_profile_note_length",
        ),
        CheckConstraint("version >= 1", name="ck_school_person_profile_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("spp"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    #: As the school typed it. Kept alongside the normalized form so an admin
    #: screen shows back what they entered, not what the database made of it.
    local_person_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The byte-stable NFKC + outer-trim form the uniqueness is enforced on.
    normalized_local_person_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: §2.4: never health, finances, a national id, a password or a token. Not
    #: enforceable by a constraint — stated here because the next person to add
    #: a field to this row needs to have read it.
    administrative_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
