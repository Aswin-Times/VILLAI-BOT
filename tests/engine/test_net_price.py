"""Take-home price per quintal: price - market deductions - transport."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.engine.net_price import net_price
from app.engine.transport import Vehicle

FLEET = (
    Vehicle("tempo", capacity_quintals=10, rate_per_km=14, min_charge=700),
    Vehicle("mini_truck", capacity_quintals=30, rate_per_km=22, min_charge=1500),
    Vehicle("truck", capacity_quintals=90, rate_per_km=35, min_charge=3000),
)


def test_worked_example() -> None:
    # 20 q goes in a mini truck: max(1500, 22 x 2 x 42) = 1,848 -> 92.40/q
    p = net_price(
        modal=2450,
        low=2200,
        high=2600,
        deductions_pct=0.08,
        qty_q=20,
        distance_km=42,
        fleet=FLEET,
    )

    assert p.gross == 2450
    assert p.deductions == pytest.approx(196)
    assert p.transport == pytest.approx(92.4)
    assert p.net == pytest.approx(2161.6)
    assert p.total == pytest.approx(43232)
    assert p.net_low == pytest.approx(2200 * 0.92 - 92.4)
    assert p.net_high == pytest.approx(2600 * 0.92 - 92.4)
    assert p.distance_km == 42


def test_missing_min_and_max_fall_back_to_modal() -> None:
    p = net_price(
        modal=2000, low=None, high=None, deductions_pct=0.0, qty_q=10, distance_km=0, fleet=FLEET
    )

    assert p.net_low == p.net == p.net_high


def test_farmer_rate_override_changes_transport() -> None:
    p = net_price(
        modal=2000,
        low=None,
        high=None,
        deductions_pct=0.0,
        qty_q=8,
        distance_km=40,
        fleet=FLEET,
        rate_per_km_override=20,
    )

    assert p.transport == pytest.approx(1600 / 8)


@given(
    modal=st.floats(min_value=100, max_value=50_000),
    pct=st.floats(min_value=0, max_value=0.2),
    qty=st.floats(min_value=0.5, max_value=500),
    km=st.floats(min_value=0, max_value=300),
)
def test_take_home_never_exceeds_the_price(modal: float, pct: float, qty: float, km: float) -> None:
    p = net_price(
        modal=modal, low=None, high=None, deductions_pct=pct, qty_q=qty, distance_km=km, fleet=FLEET
    )

    assert p.net <= p.gross
    assert p.net_low <= p.net <= p.net_high
