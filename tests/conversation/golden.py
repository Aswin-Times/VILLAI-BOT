"""Score an intent parser against tests/golden/intents.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.conversation.intents import IntentParser, ParsedIntent

GOLDEN = Path(__file__).parents[1] / "golden" / "intents.yaml"
STRICT_FIELDS = ("intent", "commodity", "quantity", "unit", "market")


@dataclass
class Miss:
    text: str
    expected: dict[str, Any]
    got: ParsedIntent


def load_golden() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    return data


def matches(expect: dict[str, Any], got: ParsedIntent) -> bool:
    for field in STRICT_FIELDS:
        want = expect.get(field)
        have = getattr(got, field)
        if field == "quantity" and want is not None and have is not None:
            if abs(float(want) - have) > 1e-9:
                return False
        elif want != have:
            return False
    if "location_text" in expect:
        return (got.location_text or "").casefold() == str(expect["location_text"]).casefold()
    return True


def score(parser: IntentParser) -> tuple[float, list[Miss]]:
    cases = load_golden()
    misses = [
        Miss(c["text"], c["expect"], got)
        for c in cases
        if not matches(c["expect"], got := parser.parse(c["text"]))
    ]
    return 1 - len(misses) / len(cases), misses
