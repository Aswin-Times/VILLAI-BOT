"""Request/response models for /v1/advice. Money is ₹ (per quintal unless named total)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class AdviceRequest(BaseModel):
    commodity: str = Field(min_length=1, max_length=64, description="Code, English or Tamil name")
    quantity: float = Field(gt=0, le=100_000)
    unit: str = Field(default="quintal", max_length=16)
    # Rough bounding box of India: anything outside is a bad location, not a farmer.
    lat: float = Field(ge=6.0, le=37.5)
    lon: float = Field(ge=68.0, le=97.5)
    rate_per_km: float | None = Field(default=None, gt=0, description="Farmer's own vehicle rate")


class GlutOut(BaseModel):
    flagged: bool
    arrivals_tonnes: float | None
    baseline_tonnes: float | None
    pct_above_normal: float | None
    reason: str | None


class MarketOption(BaseModel):
    market_code: str
    market_name: str
    obs_date: date
    stale: bool
    distance_km: float
    modal_price: float
    deductions_per_q: float
    transport_per_q: float
    net_per_q: float
    net_per_q_low: float
    net_per_q_high: float
    total_net: float
    glut: GlutOut


class AdviceResponse(BaseModel):
    recommendation_id: int
    commodity_code: str
    quantity_quintals: float
    data_as_of: date | None
    best_market_code: str | None
    nearest_market_code: str | None
    extra_vs_nearest: float | None
    options: list[MarketOption]
    regional_glut: bool
    excluded: dict[str, str]
    warnings: list[str]
