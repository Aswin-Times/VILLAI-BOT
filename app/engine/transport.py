"""Transport cost of taking a load to a mandi and back."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Vehicle:
    code: str
    capacity_quintals: float
    rate_per_km: float
    min_charge: float


def plan_trips(quantity_q: float, fleet: Sequence[Vehicle]) -> list[Vehicle]:
    """Fill the biggest vehicle while the load exceeds it, then the smallest that fits."""
    if not fleet:
        raise ValueError("no vehicles configured")
    if quantity_q <= 0:
        raise ValueError("quantity must be positive")
    by_size = sorted(fleet, key=lambda v: v.capacity_quintals)
    largest = by_size[-1]
    trips: list[Vehicle] = []
    remaining = quantity_q
    while remaining > largest.capacity_quintals:
        trips.append(largest)
        remaining -= largest.capacity_quintals
    if remaining > 0:
        trips.append(next(v for v in by_size if v.capacity_quintals >= remaining))
    return trips


def transport_cost(
    quantity_q: float,
    one_way_km: float,
    fleet: Sequence[Vehicle],
    rate_per_km_override: float | None = None,
) -> float:
    """Total ₹ for all trips; each trip is a round trip, at least its minimum charge."""
    if one_way_km < 0:
        raise ValueError("distance can't be negative")
    total = 0.0
    for v in plan_trips(quantity_q, fleet):
        rate = rate_per_km_override if rate_per_km_override is not None else v.rate_per_km
        total += max(v.min_charge, rate * 2 * one_way_km)
    return total
