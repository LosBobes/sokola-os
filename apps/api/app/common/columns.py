"""Column helpers shared across models.

We store enums as VARCHAR with a CHECK constraint (``native_enum=False``) rather
than native PostgreSQL enum types. This keeps enum evolution a plain data concern
and keeps Alembic migrations simple and reversible, while the ORM still exposes
real Python enum values.
"""

from __future__ import annotations

import enum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

E = TypeVar("E", bound=enum.Enum)


def enum_type(enum_cls: type[E], *, length: int = 40) -> SAEnum:
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        validate_strings=True,
        values_callable=lambda c: [m.value for m in c],
    )
