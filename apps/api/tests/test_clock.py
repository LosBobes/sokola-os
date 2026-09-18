"""The clock port: UTC-aware instants, freezable for tests, always restored."""

from __future__ import annotations

import datetime as dt

import pytest
from app.platform import clock


def test_now_is_timezone_aware_utc() -> None:
    instant = clock.now()
    assert instant.tzinfo is not None
    assert instant.utcoffset() == dt.timedelta(0)


def test_frozen_at_pins_now_and_today() -> None:
    with clock.frozen_at("2026-08-31T09:00:00+00:00") as frozen:
        assert clock.now() == frozen
        assert clock.now() == dt.datetime(2026, 8, 31, 9, 0, tzinfo=dt.UTC)
        assert clock.today() == dt.date(2026, 8, 31)


def test_frozen_at_normalizes_a_non_utc_instant() -> None:
    plus_two = dt.timezone(dt.timedelta(hours=2))
    with clock.frozen_at(dt.datetime(2026, 8, 31, 11, 0, tzinfo=plus_two)):
        assert clock.now() == dt.datetime(2026, 8, 31, 9, 0, tzinfo=dt.UTC)


def test_frozen_at_restores_the_previous_provider() -> None:
    before = clock.now()
    with clock.frozen_at("2020-01-01T00:00:00+00:00"):
        assert clock.now().year == 2020
    assert clock.now() >= before


def test_frozen_at_restores_the_provider_even_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError), clock.frozen_at("2020-01-01T00:00:00+00:00"):
        raise RuntimeError("boom")
    assert clock.now().year != 2020


def test_frozen_at_nests() -> None:
    with clock.frozen_at("2026-01-01T00:00:00+00:00"):
        with clock.frozen_at("2027-01-01T00:00:00+00:00"):
            assert clock.now().year == 2027
        assert clock.now().year == 2026


def test_frozen_at_rejects_a_naive_instant() -> None:
    naive = dt.datetime(2026, 8, 31, 9, 0)  # noqa: DTZ001 - a naive instant is the point here
    with pytest.raises(ValueError, match="timezone-aware"), clock.frozen_at(naive):
        pass
