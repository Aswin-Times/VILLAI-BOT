"""Distances: straight-line haversine, scaled up to approximate roads."""

from __future__ import annotations

import pytest

from app.engine.geo import ROAD_FACTOR, haversine_km, road_distance_km


def test_one_degree_of_longitude_at_the_equator() -> None:
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)


def test_same_point_is_zero() -> None:
    assert haversine_km(10.36, 77.97, 10.36, 77.97) == 0


def test_symmetric() -> None:
    a = haversine_km(10.3624, 77.9695, 10.4870, 77.7480)
    b = haversine_km(10.4870, 77.7480, 10.3624, 77.9695)
    assert a == pytest.approx(b)


def test_dindigul_to_oddanchatram_is_about_28_km_straight() -> None:
    assert haversine_km(10.3624, 77.9695, 10.4870, 77.7480) == pytest.approx(27.9, abs=0.5)


def test_road_distance_applies_the_road_factor() -> None:
    straight = haversine_km(10.3624, 77.9695, 10.4870, 77.7480)
    assert ROAD_FACTOR == 1.3
    assert road_distance_km(10.3624, 77.9695, 10.4870, 77.7480) == pytest.approx(straight * 1.3)
