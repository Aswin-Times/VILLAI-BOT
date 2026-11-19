"""Normalisation helpers for source names."""

from __future__ import annotations

import re

_UZHAVAR = re.compile(r"uzhavar\s+sandhai", re.IGNORECASE)


def is_uzhavar_sandhai(market_name: str) -> bool:
    """Uzhavar Sandhai are state-run farmers' markets selling retail in small lots.

    Their prices are farmer-to-consumer prices, and a farmer can't sell a
    truckload there, so they must never be ranked as a place to sell bulk produce.
    """
    return bool(_UZHAVAR.search(market_name))
