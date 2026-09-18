"""Clock port: the single source of "now" for business code.

Business rules that depend on the current instant (what counts as *upcoming*,
when a token expires, when a batch was committed) must read the clock through
this port rather than calling :func:`datetime.datetime.now` directly. Two
reasons, both of which bit us before this port existed:

* a direct ``dt.datetime.now(tz=dt.UTC)`` makes the surrounding behaviour
  untestable at a chosen instant, so tests either assert nothing about time or
  quietly depend on the wall clock of the machine running them;
* an accidental naive ``datetime`` reaches the database as a bare timestamp and
  silently loses the UTC contract every stored instant is supposed to carry.

Every instant this module hands out is timezone-aware UTC. Tests freeze it with
:func:`frozen_at`; nothing else may replace the provider.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator
from contextlib import contextmanager


def _system_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


_provider: Callable[[], dt.datetime] = _system_now


def now() -> dt.datetime:
    """The current instant, always timezone-aware UTC."""
    instant = _provider()
    if instant.tzinfo is None:
        raise RuntimeError("clock provider returned a naive datetime; UTC is required")
    return instant.astimezone(dt.UTC)


def today() -> dt.date:
    """The current date in UTC.

    Callers that need a *tenant-local* date must convert :func:`now` with the
    tenant's IANA zone instead: UTC midnight is not the tenant's midnight.
    """
    return now().date()


@contextmanager
def frozen_at(instant: dt.datetime | str) -> Iterator[dt.datetime]:
    """Freeze the clock at ``instant`` for the duration of the block (tests only).

    ``instant`` must be timezone-aware, so a frozen test states the instant it
    means rather than inheriting the runner's local zone.
    """
    global _provider

    frozen = dt.datetime.fromisoformat(instant) if isinstance(instant, str) else instant
    if frozen.tzinfo is None:
        raise ValueError("frozen_at requires a timezone-aware instant")
    frozen = frozen.astimezone(dt.UTC)

    previous = _provider
    _provider = lambda: frozen  # noqa: E731 - a one-expression provider is the point
    try:
        yield frozen
    finally:
        _provider = previous
