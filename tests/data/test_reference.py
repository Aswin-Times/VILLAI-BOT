"""Invariants for the hand-curated seed files in app/data/seed/."""

from __future__ import annotations

from app.data.reference import (
    load_commodities,
    load_markets,
    load_transport_rates,
    pilot_source_commodities,
)

# Rough bounding box of Tamil Nadu (plus a margin for border mandis like Hosur).
TN_LAT = (8.0, 13.6)
TN_LON = (76.0, 80.5)


def test_pilot_crops_are_the_four_in_the_plan() -> None:
    codes = {c.code for c in load_commodities()}
    assert codes == {"tomato", "small_onion", "turmeric", "banana"}


def test_only_small_onion_and_turmeric_are_storable() -> None:
    storable = {c.code for c in load_commodities() if c.storable}
    assert storable == {"small_onion", "turmeric"}


def test_storable_crops_have_a_storage_loss_rate() -> None:
    for c in load_commodities():
        if c.storable:
            assert c.storage_loss_pct_per_week is not None
            assert 0 <= c.storage_loss_pct_per_week < 10


def test_every_crop_has_tamil_name_and_synonyms_in_three_scripts() -> None:
    for c in load_commodities():
        assert c.name_ta, c.code
        assert any(_is_tamil(s) for s in c.synonyms), f"{c.code}: no Tamil-script synonym"
        assert any(s.isascii() for s in c.synonyms), f"{c.code}: no Latin synonym"
        assert c.name_en.lower() in c.synonyms, f"{c.code}: English name missing from synonyms"


def test_synonyms_do_not_collide_between_crops() -> None:
    seen: dict[str, str] = {}
    for c in load_commodities():
        for s in c.synonyms:
            assert s not in seen, f"'{s}' maps to both {seen[s]} and {c.code}"
            seen[s] = c.code


def test_source_commodity_names_are_unique_and_ordered() -> None:
    assert pilot_source_commodities() == ["Tomato", "Onion", "Turmeric", "Banana"]


def test_markets_sit_inside_tamil_nadu() -> None:
    markets = load_markets()
    assert len(markets) >= 10
    for m in markets:
        assert TN_LAT[0] <= m.lat <= TN_LAT[1], m.code
        assert TN_LON[0] <= m.lon <= TN_LON[1], m.code


def test_market_codes_are_unique_and_deductions_are_fractions() -> None:
    markets = load_markets()
    assert len({m.code for m in markets}) == len(markets)
    for m in markets:
        assert 0 <= m.deductions_pct < 0.25, m.code


def test_market_aliases_are_unique_across_markets() -> None:
    seen: dict[str, str] = {}
    for m in load_markets():
        for alias in m.agmarknet_names:
            assert alias not in seen, f"'{alias}' used by {seen[alias]} and {m.code}"
            seen[alias] = m.code


def test_every_market_has_a_tamil_name_and_local_aliases() -> None:
    for m in load_markets():
        assert _is_tamil(m.name_ta), m.code
        assert any(_is_tamil(a) for a in m.aliases), f"{m.code}: no Tamil-script alias"
        assert m.name.lower() in m.aliases, f"{m.code}: English name missing from aliases"


def test_local_aliases_do_not_collide_between_markets() -> None:
    seen: dict[str, str] = {}
    for m in load_markets():
        for alias in m.aliases:
            assert alias not in seen, f"'{alias}' used by {seen[alias]} and {m.code}"
            seen[alias] = m.code


def test_transport_vehicles_ordered_by_capacity_with_positive_rates() -> None:
    rates = load_transport_rates()
    capacities = [v.capacity_quintals for v in rates]
    assert capacities == sorted(capacities)
    for v in rates:
        assert v.rate_per_km > 0
        assert v.min_charge >= 0


def _is_tamil(s: str) -> bool:
    return any("஀" <= ch <= "௿" for ch in s)
