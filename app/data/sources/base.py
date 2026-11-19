"""Common types for price/arrival sources.

Every source adapter returns `PriceObservation`s with prices in ₹/quintal and
arrivals in tonnes, using the names exactly as the source spells them. Mapping
source names to our markets/commodities happens later, in normalisation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class DataSourceError(RuntimeError):
    """A source could not be reached or returned an error."""


class SchemaDriftError(DataSourceError):
    """A source's response no longer has the fields we depend on."""


class PriceObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    obs_date: date
    state: str
    district: str
    market: str
    commodity: str
    variety: str
    grade: str
    min_price: float | None
    max_price: float | None
    modal_price: float | None
    arrivals_tonnes: float | None = None
    source: str


class PriceSource(Protocol):
    name: str

    def fetch(
        self, *, day: date, commodities: Sequence[str], state: str = "Tamil Nadu"
    ) -> list[PriceObservation]: ...


class HistorySource(Protocol):
    name: str

    def fetch_history(
        self, *, district: str, commodity: str, state: str = "Tamil Nadu"
    ) -> list[PriceObservation]: ...
