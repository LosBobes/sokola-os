"""Observability port: failure descriptions that carry no personal data.

§3 of the v5.7 execution contract: logs, metrics, events and dead-letter records
must not contain tokens, credentials, raw contacts, a child's name, document or
message content, bank references or amounts.

A raw exception breaks that rule routinely, and not in a way anyone notices.
SQLAlchemy appends the statement and its bound parameters to the message, and
PostgreSQL's own ``DETAIL`` adds ``Failing row contains (...)``. So a handler
that fails while inserting a notification puts the child's name and the
guardian's email into ``outbox_message.last_error`` and into the log line, from
a line of code that only says ``repr(exc)``.

The fix is not to scrub the message. Scrubbing cannot recognise that "Ana
Marković" is a name, and a redactor that silently misses is worse than none.
:func:`safe_error` instead *builds* the description from structure that is known
to be metadata: the exception type, the SQLSTATE, and the schema objects
involved. For a database error that is also the more useful diagnostic; free
text is only ever a fallback, and it is redacted and truncated.
"""

from __future__ import annotations

import re

# Best effort only, for messages we did not construct. The real guarantee is
# that structured errors never reach this path at all.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_DIGITS = re.compile(r"\d{6,}")
# SQLAlchemy appends these; both quote row values verbatim.
_SQL_BLOCK = re.compile(r"\n?\[SQL:.*?\](?=\n\[|$)", re.DOTALL)
_PARAMS_BLOCK = re.compile(r"\n?\[parameters:.*?\](?=\n\[|$)", re.DOTALL)
# PostgreSQL prints the offending row here.
_PG_DETAIL = re.compile(r"\n?DETAIL:.*?(?=\n[A-Z]+:|$)", re.DOTALL)

_MAX_MESSAGE = 300


def redact(text: str) -> str:
    """Strip the parts of a free-text message most likely to carry personal data.

    Deliberately conservative about what it claims: it removes the blocks that
    are *known* to quote row values, plus contacts and long digit runs (phone
    numbers, bank references, amounts in minor units). It cannot recognise a
    name, so callers must not rely on it as the only defence.
    """
    cleaned = _SQL_BLOCK.sub("", text)
    cleaned = _PARAMS_BLOCK.sub("", cleaned)
    cleaned = _PG_DETAIL.sub("", cleaned)
    cleaned = _EMAIL.sub("<email>", cleaned)
    cleaned = _LONG_DIGITS.sub("<digits>", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > _MAX_MESSAGE:
        cleaned = cleaned[:_MAX_MESSAGE] + "..."
    return cleaned


def safe_error(exc: BaseException) -> str:
    """A description of ``exc`` safe to log and to persist.

    For a database error this is the exception type, the SQLSTATE and the table,
    column and constraint involved, which identifies the fault precisely without
    quoting a single row value. Anything else falls back to the type plus a
    redacted message.
    """
    # SQLAlchemy wraps the driver's exception; the driver's one carries the diagnostics.
    original = getattr(exc, "orig", None)
    target: BaseException = original if isinstance(original, BaseException) else exc

    name = f"{type(target).__module__}.{type(target).__name__}"
    details: list[str] = []

    sqlstate = getattr(target, "sqlstate", None)
    if sqlstate:
        details.append(f"sqlstate={sqlstate}")

    diag = getattr(target, "diag", None)
    if diag is not None:
        for attribute, label in (
            ("table_name", "table"),
            ("column_name", "column"),
            ("constraint_name", "constraint"),
        ):
            value = getattr(diag, attribute, None)
            if value:
                details.append(f"{label}={value}")

    if details:
        return f"{name}({', '.join(details)})"

    message = redact(str(target))
    return f"{name}: {message}" if message else name
