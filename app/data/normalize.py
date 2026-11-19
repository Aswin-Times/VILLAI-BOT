"""Normalisation: match source names to our markets/commodities, flag bad rows."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from app.models import Commodity, Market

_UZHAVAR = re.compile(r"uzhavar\s+sandhai", re.IGNORECASE)
OUTLIER_FACTOR = 3.0


def is_uzhavar_sandhai(market_name: str) -> bool:
    """Uzhavar Sandhai are state-run farmers' markets selling retail in small lots.

    Their prices are farmer-to-consumer prices, and a farmer can't sell a
    truckload there, so they must never be ranked as a place to sell bulk produce.
    """
    return bool(_UZHAVAR.search(market_name))


def normalise_name(name: str) -> str:
    return " ".join(name.split()).casefold()


class MarketMatcher:
    """Exact match on (district, market alias) after normalisation. Never substring."""

    def __init__(self, markets: Iterable[Market]) -> None:
        self._index = {
            (normalise_name(m.agmarknet_district), normalise_name(alias)): m.id
            for m in markets
            for alias in m.agmarknet_names
        }

    def match(self, district: str, market: str) -> int | None:
        if is_uzhavar_sandhai(market):
            return None
        return self._index.get((normalise_name(district), normalise_name(market)))


class CommodityMatcher:
    """Match (source commodity, variety) using each commodity's variety rules."""

    def __init__(self, commodities: Iterable[Commodity]) -> None:
        self._by_name: dict[str, list[tuple[int, set[str], set[str]]]] = defaultdict(list)
        for c in commodities:
            allowed = {normalise_name(v) for v in c.agmarknet_varieties}
            excluded = {normalise_name(v) for v in c.exclude_varieties}
            self._by_name[normalise_name(c.agmarknet_commodity)].append((c.id, allowed, excluded))

    def match(self, commodity: str, variety: str) -> int | None:
        v = normalise_name(variety)
        for commodity_id, allowed, excluded in self._by_name.get(normalise_name(commodity), []):
            if v in excluded or (allowed and v not in allowed):
                continue
            return commodity_id
        return None


def quality_flags(
    min_price: float | None,
    modal_price: float | None,
    max_price: float | None,
    reference_modal: float | None = None,
) -> list[str]:
    """Problems with one price row. Flagged rows are stored, not silently dropped."""
    if modal_price is None:
        return ["missing_modal"]
    flags: list[str] = []
    present = [p for p in (min_price, modal_price, max_price) if p is not None]
    if any(p <= 0 for p in present):
        flags.append("non_positive_price")
    if (min_price is not None and min_price > modal_price) or (
        max_price is not None and modal_price > max_price
    ):
        flags.append("price_order")
    if reference_modal and (
        modal_price > reference_modal * OUTLIER_FACTOR
        or modal_price < reference_modal / OUTLIER_FACTOR
    ):
        flags.append("outlier")
    return flags
