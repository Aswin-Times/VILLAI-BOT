"""Matching source names to our markets/commodities, and row quality flags."""

from __future__ import annotations

from app.data.normalize import (
    CommodityMatcher,
    MarketMatcher,
    normalise_name,
    quality_flags,
)
from app.models import Commodity, Market


def market(id_: int, code: str, district: str, names: list[str]) -> Market:
    return Market(
        id=id_,
        code=code,
        name=code.title(),
        district=district,
        agmarknet_district=district,
        lat=10.0,
        lon=77.0,
        agmarknet_names=names,
        market_type="wholesale",
        deductions_pct=0.08,
    )


def commodity(
    id_: int, code: str, source: str, varieties: list[str], exclude: list[str] | None = None
) -> Commodity:
    return Commodity(
        id=id_,
        code=code,
        name_en=code,
        name_ta=code,
        agmarknet_commodity=source,
        agmarknet_varieties=varieties,
        exclude_varieties=exclude or [],
        synonyms=[code],
        storable=False,
    )


MARKETS = MarketMatcher(
    [
        market(1, "oddanchatram", "Dindigul", ["Oddanchatram", "Oddunchairum"]),
        market(2, "palani", "Dindigul", ["Palani"]),
        market(3, "udumalpet", "Thiruppur", ["Udumalpettai RM"]),
    ]
)
COMMODITIES = CommodityMatcher(
    [
        commodity(1, "tomato", "Tomato", []),
        commodity(2, "small_onion", "Onion", [], exclude=["Bellary"]),
        commodity(3, "turmeric", "Turmeric", ["Finger", "Bulb"]),
    ]
)


def test_normalise_collapses_space_and_case() -> None:
    assert normalise_name("  Udumalpettai   RM ") == "udumalpettai rm"


def test_matches_any_alias_ignoring_case_and_spacing() -> None:
    assert MARKETS.match("Dindigul", "Oddunchairum") == 1
    assert MARKETS.match("dindigul", " ODDANCHATRAM ") == 1
    assert MARKETS.match("Thiruppur", "Udumalpettai  RM") == 3


def test_district_must_match_too() -> None:
    assert MARKETS.match("Salem", "Palani") is None


def test_retail_market_with_a_similar_name_never_matches() -> None:
    assert MARKETS.match("Dindigul", "Palani(Uzhavar Sandhai )") is None


def test_commodity_any_variety() -> None:
    assert COMMODITIES.match("Tomato", "Deshi") == 1
    assert COMMODITIES.match("tomato", "Hybrid") == 1


def test_commodity_excluded_variety_does_not_match() -> None:
    assert COMMODITIES.match("Onion", "Bellary") is None
    assert COMMODITIES.match("Onion", "Local") == 2


def test_commodity_listed_varieties_only() -> None:
    assert COMMODITIES.match("Turmeric", "finger") == 3
    assert COMMODITIES.match("Turmeric", "Other") is None


def test_unknown_commodity() -> None:
    assert COMMODITIES.match("Brinjal", "Local") is None


def test_clean_row_has_no_flags() -> None:
    assert quality_flags(2000, 2200, 2500) == []


def test_flags_min_above_modal_or_modal_above_max() -> None:
    assert quality_flags(2300, 2200, 2500) == ["price_order"]
    assert quality_flags(2000, 2600, 2500) == ["price_order"]


def test_flags_missing_or_non_positive_prices() -> None:
    assert quality_flags(None, None, None) == ["missing_modal"]
    assert quality_flags(0, 0, 0) == ["non_positive_price"]


def test_flags_prices_far_from_the_reference() -> None:
    assert quality_flags(9000, 9500, 9900, reference_modal=2500) == ["outlier"]
    assert quality_flags(500, 600, 700, reference_modal=2500) == ["outlier"]
    assert quality_flags(2000, 2400, 2600, reference_modal=2500) == []
