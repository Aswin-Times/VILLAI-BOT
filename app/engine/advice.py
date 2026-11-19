"""Full advice for one request: ranked mandis, glut signals and warnings.

Pure: the caller passes in the latest quote per mandi and each mandi's daily
arrivals. Hold/sell for storable crops is added in Phase 4.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.engine.glut import (
    DEFAULT_GLUT_THRESHOLDS,
    GlutSignal,
    GlutThresholds,
    RegionalGlut,
    detect_glut,
    regional_glut,
)
from app.engine.ranking import MarketQuote, Ranking, rank_markets
from app.engine.transport import Vehicle


@dataclass(frozen=True)
class Advice:
    ranking: Ranking
    gluts: dict[str, GlutSignal]  # market_code -> signal, for every candidate
    regional: RegionalGlut
    warnings: list[str]  # no_recent_data | stale_data


def advise(
    quotes: Sequence[MarketQuote],
    arrivals: Mapping[str, Mapping[date, float]],
    *,
    qty_q: float,
    farmer_lat: float,
    farmer_lon: float,
    fleet: Sequence[Vehicle],
    today: date,
    top_n: int = 3,
    rate_per_km_override: float | None = None,
    glut_thresholds: GlutThresholds = DEFAULT_GLUT_THRESHOLDS,
) -> Advice:
    ranking = rank_markets(
        quotes,
        qty_q=qty_q,
        farmer_lat=farmer_lat,
        farmer_lon=farmer_lon,
        fleet=fleet,
        today=today,
        top_n=top_n,
        rate_per_km_override=rate_per_km_override,
    )
    gluts = {
        c.quote.market_code: detect_glut(
            c.quote.market_code,
            arrivals.get(c.quote.market_code, {}),
            c.quote.obs_date,
            glut_thresholds,
        )
        for c in ranking.candidates
    }
    warnings: list[str] = []
    if not ranking.options:
        warnings.append("no_recent_data")
    elif ranking.best is None:
        warnings.append("stale_data")
    return Advice(
        ranking=ranking,
        gluts=gluts,
        regional=regional_glut(list(gluts.values())),
        warnings=warnings,
    )
