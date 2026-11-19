"""Tests for the market x commodity coverage report used for go/no-go."""

from __future__ import annotations

from datetime import date, timedelta

from app.data.coverage import coverage_table, render_markdown
from app.data.normalize import is_uzhavar_sandhai
from app.data.sources.base import PriceObservation

TODAY = date(2026, 11, 19)


def obs(day: date, market: str = "Oddanchatram", commodity: str = "Tomato") -> PriceObservation:
    return PriceObservation(
        obs_date=day,
        state="Tamil Nadu",
        district="Dindigul",
        market=market,
        commodity=commodity,
        variety="Deshi",
        grade="FAQ",
        min_price=1800.0,
        max_price=2600.0,
        modal_price=2200.0,
        source="datagov",
    )


def test_recognises_uzhavar_sandhai_names_with_odd_spacing() -> None:
    assert is_uzhavar_sandhai("Palani(Uzhavar Sandhai )")
    assert is_uzhavar_sandhai("Kodaikkanal(Uzhavar Sandhai)")
    assert is_uzhavar_sandhai("Tiruppur (North) (Uzhavar  Sandhai )")
    assert not is_uzhavar_sandhai("Udumalpettai RM")
    assert not is_uzhavar_sandhai("Palani")


def test_counts_distinct_days_inside_the_window_only() -> None:
    rows = [
        obs(TODAY - timedelta(days=1)),
        obs(TODAY - timedelta(days=1)),  # second variety same day: still one day
        obs(TODAY - timedelta(days=10)),
        obs(TODAY - timedelta(days=400)),  # outside a 365-day window
    ]

    (row,) = coverage_table(rows, today=TODAY, window_days=365)

    assert row.days_reported == 2
    assert row.last_reported == TODAY - timedelta(days=1)


def test_flags_retail_markets_and_sorts_busiest_first() -> None:
    rows = [
        obs(TODAY - timedelta(days=d), market="Palani(Uzhavar Sandhai )") for d in range(1, 4)
    ] + [obs(TODAY - timedelta(days=d), market="Oddanchatram") for d in range(1, 6)]

    table = coverage_table(rows, today=TODAY, window_days=365)

    assert [(r.market, r.retail) for r in table] == [
        ("Oddanchatram", False),
        ("Palani(Uzhavar Sandhai )", True),
    ]


def test_markdown_lists_each_market_row() -> None:
    table = coverage_table([obs(TODAY - timedelta(days=2))], today=TODAY, window_days=365)

    md = render_markdown(table, today=TODAY, window_days=365)

    assert "| Dindigul | Oddanchatram | Tomato | 1 | 2026-11-17 | wholesale |" in md
