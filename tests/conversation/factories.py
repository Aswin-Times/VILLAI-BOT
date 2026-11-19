"""Shared builders for conversation tests."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.schemas.advice import AdviceResponse, GlutOut, MarketOption


def option(code: str, name: str, net: float, km: float, **kw: Any) -> MarketOption:
    base: dict[str, Any] = {
        "market_code": code,
        "market_name": name,
        "obs_date": date(2026, 11, 18),
        "stale": False,
        "distance_km": km,
        "modal_price": 2450.0,
        "deductions_per_q": 196.0,
        "transport_per_q": 92.4,
        "net_per_q": net,
        "net_per_q_low": net - 100,
        "net_per_q_high": net + 100,
        "total_net": net * 20,
        "glut": GlutOut(
            flagged=False,
            arrivals_tonnes=None,
            baseline_tonnes=None,
            pct_above_normal=None,
            reason="no_arrivals_today",
        ),
    }
    base.update(kw)
    return MarketOption.model_validate(base)


def advice_response(**kw: Any) -> AdviceResponse:
    spike = GlutOut(
        flagged=True, arrivals_tonnes=270, baseline_tonnes=187.5, pct_above_normal=44.0, reason=None
    )
    base: dict[str, Any] = {
        "recommendation_id": 1,
        "commodity_code": "tomato",
        "quantity_quintals": 20,
        "data_as_of": date(2026, 11, 18),
        "best_market_code": "oddanchatram",
        "nearest_market_code": "dindigul",
        "extra_vs_nearest": 2739.35,
        "options": [
            option("oddanchatram", "Oddanchatram", 2316.04, 34.6, glut=spike),
            option("dindigul", "Dindigul", 2179.0, 1.7),
            option("palani", "Palani", 2158.85, 64.2),
        ],
        "regional_glut": False,
        "excluded": {},
        "warnings": [],
    }
    base.update(kw)
    return AdviceResponse.model_validate(base)
