"""Transport cost: pick vehicles for the load, charge a round trip per vehicle."""

from __future__ import annotations

import pytest

from app.engine.transport import Vehicle, plan_trips, transport_cost

TEMPO = Vehicle("tempo", capacity_quintals=10, rate_per_km=14, min_charge=700)
MINI = Vehicle("mini_truck", capacity_quintals=30, rate_per_km=22, min_charge=1500)
TRUCK = Vehicle("truck", capacity_quintals=90, rate_per_km=35, min_charge=3000)
FLEET = (TEMPO, MINI, TRUCK)


def test_smallest_vehicle_that_fits() -> None:
    assert plan_trips(8, FLEET) == [TEMPO]
    assert plan_trips(10, FLEET) == [TEMPO]
    assert plan_trips(20, FLEET) == [MINI]


def test_big_loads_fill_lorries_then_fit_the_remainder() -> None:
    assert plan_trips(200, FLEET) == [TRUCK, TRUCK, MINI]
    assert plan_trips(180, FLEET) == [TRUCK, TRUCK]


def test_fleet_order_does_not_matter() -> None:
    assert plan_trips(20, (TRUCK, TEMPO, MINI)) == [MINI]


def test_round_trip_rate_above_minimum() -> None:
    # 14/km x 2 x 40 km = 1,120 > 700 minimum
    assert transport_cost(8, 40, FLEET) == 1120


def test_short_trip_pays_the_minimum_charge() -> None:
    assert transport_cost(8, 10, FLEET) == 700


def test_several_vehicles_add_up() -> None:
    # 2 lorries x max(3000, 35 x 100) + 1 mini truck x max(1500, 22 x 100)
    assert transport_cost(200, 50, FLEET) == 2 * 3500 + 2200


def test_farmer_rate_overrides_the_table_rate() -> None:
    assert transport_cost(8, 40, FLEET, rate_per_km_override=20) == 1600


def test_rejects_empty_fleet_and_bad_inputs() -> None:
    with pytest.raises(ValueError):
        plan_trips(8, ())
    with pytest.raises(ValueError):
        plan_trips(0, FLEET)
    with pytest.raises(ValueError):
        transport_cost(8, -1, FLEET)
