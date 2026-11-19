"""Load the hand-curated reference data in app/data/seed/."""

from __future__ import annotations

import csv
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

SEED_DIR = Path(__file__).parent / "seed"


class Commodity(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name_en: str
    name_ta: str
    agmarknet_commodity: str
    agmarknet_varieties: tuple[str, ...] = ()
    exclude_varieties: tuple[str, ...] = ()
    mapping_verified: bool = False
    storable: bool
    storage_loss_pct_per_week: float | None = None
    pack_weights_kg: dict[str, float] = {}
    synonyms: tuple[str, ...]

    @field_validator("synonyms")
    @classmethod
    def _normalise_synonyms(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(" ".join(s.lower().split()) for s in v)


class Market(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    district: str
    agmarknet_district: str
    lat: float
    lon: float
    agmarknet_names: tuple[str, ...]
    market_type: Literal["wholesale", "regulated"]
    deductions_pct: float
    verified: bool
    notes: str = ""


class Vehicle(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name_en: str
    name_ta: str
    capacity_quintals: float
    rate_per_km: float
    min_charge: float


@cache
def load_commodities(path: Path = SEED_DIR / "commodities.yaml") -> tuple[Commodity, ...]:
    raw: list[dict[str, Any]] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(Commodity.model_validate(c) for c in raw)


def pilot_source_commodities() -> list[str]:
    """Agmarknet commodity names to fetch, de-duplicated, in seed order."""
    return list(dict.fromkeys(c.agmarknet_commodity for c in load_commodities()))


@cache
def load_markets(path: Path = SEED_DIR / "markets.csv") -> tuple[Market, ...]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return tuple(
        Market.model_validate(
            {
                **row,
                "agmarknet_names": tuple(n.strip() for n in row["agmarknet_names"].split(";")),
                "verified": row["verified"].strip().lower() == "true",
            }
        )
        for row in rows
    )


@cache
def load_transport_rates(path: Path = SEED_DIR / "transport_rates.yaml") -> tuple[Vehicle, ...]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(Vehicle.model_validate(v) for v in raw["vehicles"])
