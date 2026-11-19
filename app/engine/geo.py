"""Distances between a farmer and a mandi."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0
# v1 approximation of road distance from straight-line distance (plan §6.1);
# replace with OSRM routing later.
ROAD_FACTOR = 1.3


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = p2 - p1, radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def road_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_km(lat1, lon1, lat2, lon2) * ROAD_FACTOR
