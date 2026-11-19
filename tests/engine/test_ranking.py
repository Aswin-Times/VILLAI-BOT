"""Ranking mandis by what the farmer takes home (plan §6.1, §6.5)."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.engine.geo import road_distance_km
from app.engine.net_price import net_price
from app.engine.ranking import MarketQuote, Ranking, rank_markets
from app.engine.transport import Vehicle

TODAY = date(2026, 11, 19)
YESTERDAY = TODAY - timedelta(days=1)
FARMER = (10.40, 77.90)
FLEET = (
    Vehicle("tempo", capacity_quintals=10, rate_per_km=14, min_charge=700),
    Vehicle("mini_truck", capacity_quintals=30, rate_per_km=22, min_charge=1500),
    Vehicle("truck", capacity_quintals=90, rate_per_km=35, min_charge=3000),
)


def quote(
    code: str,
    lat: float,
    lon: float,
    modal: float | None,
    obs_date: date = YESTERDAY,
    deductions_pct: float = 0.08,
) -> MarketQuote:
    return MarketQuote(
        market_code=code,
        market_name=code.title(),
        lat=lat,
        lon=lon,
        deductions_pct=deductions_pct,
        obs_date=obs_date,
        min_price=None if modal is None else modal - 100,
        modal_price=modal,
        max_price=None if modal is None else modal + 100,
    )


NEAR = quote("near", 10.42, 77.92, 2300)  # ~4 km by road
FAR = quote("far", 10.95, 77.95, 2350)  # ~80 km: slightly higher price, much more transport


def rank(quotes: list[MarketQuote], qty_q: float = 8, **kwargs: Any) -> Ranking:
    return rank_markets(
        quotes,
        qty_q=qty_q,
        farmer_lat=FARMER[0],
        farmer_lon=FARMER[1],
        fleet=FLEET,
        today=TODAY,
        **kwargs,
    )


def codes(r: Ranking) -> list[str]:
    return [o.quote.market_code for o in r.options]


def test_ranks_by_take_home_not_headline_price() -> None:
    assert codes(rank([FAR, NEAR])) == ["near", "far"]


def test_take_home_matches_the_net_price_formula() -> None:
    r = rank([NEAR])
    km = road_distance_km(*FARMER, NEAR.lat, NEAR.lon)

    expected = net_price(
        modal=2300, low=2200, high=2400, deductions_pct=0.08, qty_q=8, distance_km=km, fleet=FLEET
    )

    assert r.options[0].price == expected


def test_higher_price_wins_when_transport_does_not_eat_it() -> None:
    nearby_better = quote("better", 10.43, 77.93, 2600)

    r = rank([NEAR, nearby_better])

    assert r.best is not None
    assert r.best.quote.market_code == "better"


def test_markets_beyond_the_radius_are_excluded_with_a_reason() -> None:
    hosur = quote("hosur", 12.74, 77.83, 4000)

    r = rank([NEAR, hosur])

    assert codes(r) == ["near"]
    assert r.excluded == {"hosur": "too_far"}


def test_stale_quotes_rank_below_fresh_ones_even_if_they_pay_more() -> None:
    stale_rich = quote("stale", 10.43, 77.93, 3500, obs_date=TODAY - timedelta(days=5))

    r = rank([stale_rich, NEAR])

    assert [(o.quote.market_code, o.stale) for o in r.options] == [("near", False), ("stale", True)]
    assert r.best is not None
    assert r.best.quote.market_code == "near"


def test_no_best_choice_when_every_quote_is_stale() -> None:
    old = quote("old", 10.43, 77.93, 2500, obs_date=TODAY - timedelta(days=6))

    r = rank([old])

    assert r.best is None
    assert r.options[0].stale


def test_very_old_and_unpriced_quotes_are_dropped() -> None:
    ancient = quote("ancient", 10.43, 77.93, 2500, obs_date=TODAY - timedelta(days=20))
    unpriced = quote("unpriced", 10.43, 77.93, None)

    r = rank([ancient, unpriced, NEAR])

    assert codes(r) == ["near"]
    assert r.excluded == {"ancient": "too_old", "unpriced": "no_price"}


def test_extra_take_home_versus_the_nearest_mandi() -> None:
    nearby_better = quote("better", 10.43, 77.93, 2600)

    r = rank([NEAR, nearby_better])

    assert r.nearest is not None
    assert r.nearest.quote.market_code == "near"
    assert r.best is not None
    assert r.extra_vs_nearest == pytest.approx(r.best.price.total - r.nearest.price.total)
    assert r.extra_vs_nearest is not None and r.extra_vs_nearest > 0


def test_equal_take_home_prefers_fresher_data() -> None:
    a = quote("a_older", 10.42, 77.92, 2300, obs_date=TODAY - timedelta(days=3))
    b = quote("b_newer", 10.42, 77.92, 2300, obs_date=TODAY)

    assert codes(rank([a, b])) == ["b_newer", "a_older"]


def test_top_n_limits_the_options_shown() -> None:
    quotes = [quote(f"m{i}", 10.40 + i * 0.01, 77.90, 2000 + i) for i in range(6)]

    assert len(rank(quotes, top_n=3).options) == 3


def test_candidates_keep_every_eligible_market_in_rank_order() -> None:
    quotes = [quote(f"m{i}", 10.40 + i * 0.01, 77.90, 2000 + i) for i in range(5)]

    r = rank(quotes, top_n=2)

    assert len(r.candidates) == 5
    assert r.options == r.candidates[:2]


def test_data_as_of_is_the_newest_date_shown() -> None:
    older = quote("older", 10.43, 77.93, 2600, obs_date=TODAY - timedelta(days=2))

    assert rank([older, NEAR]).data_as_of == YESTERDAY


def test_empty_input_gives_empty_ranking() -> None:
    r = rank([])

    assert r.options == []
    assert r.best is None
    assert r.data_as_of is None


market_strategy = st.builds(
    quote,
    code=st.text(alphabet="abcdefghij", min_size=1, max_size=6),
    lat=st.floats(min_value=10.0, max_value=10.8),
    lon=st.floats(min_value=77.5, max_value=78.3),
    modal=st.floats(min_value=500, max_value=9000),
    obs_date=st.integers(min_value=0, max_value=10).map(lambda d: TODAY - timedelta(days=d)),
)
markets_strategy = st.lists(market_strategy, max_size=8, unique_by=lambda q: q.market_code)


@given(markets_strategy)
def test_order_of_input_never_changes_the_ranking(quotes: list[MarketQuote]) -> None:
    shuffled = quotes[:]
    random.Random(42).shuffle(shuffled)

    assert rank(quotes, top_n=10) == rank(shuffled, top_n=10)


@given(markets_strategy)
def test_a_stale_quote_is_never_first(quotes: list[MarketQuote]) -> None:
    r = rank(quotes, top_n=10)

    if r.best is not None:
        assert not r.best.stale
    if r.options and r.options[0].stale:
        assert all(o.stale for o in r.options)
