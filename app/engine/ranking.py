"""Rank mandis by take-home price (plan §6.1, guardrails §6.5).

Rules:
- Only mandis within `max_radius_km` by road, with a price no older than `max_age_days`.
- Fresh quotes (reported within 3 days) rank above stale ones, whatever they pay.
  A stale quote is shown and marked, but is never the recommended choice.
- Ties: fresher data, then nearer, then market code (so the order is deterministic).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from app.engine.freshness import STALE_AFTER_DAYS, age_days
from app.engine.geo import road_distance_km
from app.engine.net_price import NetPrice, net_price
from app.engine.transport import Vehicle

DEFAULT_RADIUS_KM = 100.0
DEFAULT_MAX_AGE_DAYS = 14


@dataclass(frozen=True)
class MarketQuote:
    """The latest price for one commodity at one mandi, in ₹/quintal."""

    market_code: str
    market_name: str
    lat: float
    lon: float
    deductions_pct: float
    obs_date: date
    min_price: float | None
    modal_price: float | None
    max_price: float | None


@dataclass(frozen=True)
class RankedMarket:
    quote: MarketQuote
    price: NetPrice
    stale: bool
    age_days: int


@dataclass(frozen=True)
class Ranking:
    options: list[RankedMarket]
    best: RankedMarket | None  # None when no fresh quote is available
    nearest: RankedMarket | None  # nearest fresh quote
    extra_vs_nearest: float | None  # ₹ total, best vs nearest
    data_as_of: date | None  # newest price date among the options
    excluded: dict[str, str]  # market_code -> reason


def rank_markets(
    quotes: Iterable[MarketQuote],
    *,
    qty_q: float,
    farmer_lat: float,
    farmer_lon: float,
    fleet: Sequence[Vehicle],
    today: date,
    max_radius_km: float = DEFAULT_RADIUS_KM,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    stale_after_days: int = STALE_AFTER_DAYS,
    top_n: int = 3,
    rate_per_km_override: float | None = None,
) -> Ranking:
    candidates: list[RankedMarket] = []
    excluded: dict[str, str] = {}
    for q in quotes:
        if q.modal_price is None:
            excluded[q.market_code] = "no_price"
            continue
        age = age_days(q.obs_date, today)
        if age > max_age_days:
            excluded[q.market_code] = "too_old"
            continue
        km = road_distance_km(farmer_lat, farmer_lon, q.lat, q.lon)
        if km > max_radius_km:
            excluded[q.market_code] = "too_far"
            continue
        price = net_price(
            modal=q.modal_price,
            low=q.min_price,
            high=q.max_price,
            deductions_pct=q.deductions_pct,
            qty_q=qty_q,
            distance_km=km,
            fleet=fleet,
            rate_per_km_override=rate_per_km_override,
        )
        candidates.append(RankedMarket(q, price, age > stale_after_days, age))

    ordered = sorted(
        candidates,
        key=lambda r: (r.stale, -r.price.net, r.age_days, r.price.distance_km, r.quote.market_code),
    )
    options = ordered[:top_n]
    best = options[0] if options and not options[0].stale else None
    nearest = min(
        (c for c in candidates if not c.stale),
        key=lambda r: (r.price.distance_km, r.quote.market_code),
        default=None,
    )
    extra = best.price.total - nearest.price.total if best and nearest else None
    return Ranking(
        options=options,
        best=best,
        nearest=nearest,
        extra_vs_nearest=extra,
        data_as_of=max((o.quote.obs_date for o in options), default=None),
        excluded=excluded,
    )
