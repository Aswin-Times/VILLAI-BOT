"""What the farmer takes home per quintal at one mandi (plan §6.1).

    deductions = price x deductions_pct          (market fee, commission)
    transport  = round-trip vehicle cost / qty
    net        = price - deductions - transport
    total      = net x qty

`net_low`/`net_high` repeat the sum with the day's min/max price so callers can
show a range instead of an over-precise single number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.engine.transport import Vehicle, transport_cost


@dataclass(frozen=True)
class NetPrice:
    gross: float
    deductions: float
    transport: float
    net: float
    net_low: float
    net_high: float
    total: float
    distance_km: float


def net_price(
    *,
    modal: float,
    low: float | None,
    high: float | None,
    deductions_pct: float,
    qty_q: float,
    distance_km: float,
    fleet: Sequence[Vehicle],
    rate_per_km_override: float | None = None,
) -> NetPrice:
    transport = transport_cost(qty_q, distance_km, fleet, rate_per_km_override) / qty_q

    def take_home(price: float) -> float:
        return price * (1 - deductions_pct) - transport

    net = take_home(modal)
    net_low = take_home(low if low is not None else modal)
    net_high = take_home(high if high is not None else modal)
    return NetPrice(
        gross=modal,
        deductions=modal * deductions_pct,
        transport=transport,
        net=net,
        # Bad source rows can have min > modal; never show a range that excludes `net`.
        net_low=min(net_low, net),
        net_high=max(net_high, net),
        total=net * qty_q,
        distance_km=distance_km,
    )
