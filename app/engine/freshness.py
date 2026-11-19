"""How old a price is, and when it counts as stale (plan §4.4)."""

from __future__ import annotations

from datetime import date

STALE_AFTER_DAYS = 3


def age_days(obs_date: date, today: date) -> int:
    return (today - obs_date).days


def is_stale(obs_date: date, today: date, stale_after_days: int = STALE_AFTER_DAYS) -> bool:
    return age_days(obs_date, today) > stale_after_days
