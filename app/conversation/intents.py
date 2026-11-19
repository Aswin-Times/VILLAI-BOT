"""What a farmer's message asks for, as structured fields.

Parsers only fill these fields. They never produce reply text or numbers for
the farmer: replies come from templates filled by the engine (CLAUDE.md).
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal[
    "advice",  # where to sell
    "price",  # today's price at one mandi
    "help",
    "alert",
    "stop",
    "change_crops",
    "change_location",
    "language",
    "greeting",
    "yes",
    "no",
    "unknown",
]
Unit = Literal["quintal", "kg", "tonne", "bag", "crate"]


class ParsedIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: Intent
    commodity: str | None = None  # commodity code, e.g. "small_onion"
    quantity: float | None = Field(default=None, gt=0)
    unit: Unit | None = None
    location_text: str | None = None  # a place the farmer named for themselves
    market: str | None = None  # market code, for price-at-one-mandi questions


class IntentParser(Protocol):
    name: str

    def parse(self, text: str) -> ParsedIntent: ...
