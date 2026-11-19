"""Data older than 3 days is stale (plan §4.4)."""

from __future__ import annotations

from datetime import date

from app.engine.freshness import STALE_AFTER_DAYS, age_days, is_stale

TODAY = date(2026, 11, 19)


def test_age_in_days() -> None:
    assert age_days(date(2026, 11, 18), TODAY) == 1


def test_three_days_old_is_still_fresh_four_is_stale() -> None:
    assert STALE_AFTER_DAYS == 3
    assert not is_stale(date(2026, 11, 16), TODAY)
    assert is_stale(date(2026, 11, 15), TODAY)
