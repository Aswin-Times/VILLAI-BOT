"""Turn a place name into coordinates.

v1 knows the pilot's market towns (with their Tamil and local names). Pincode
lookup (India Post directory) is a follow-up; until then an unknown place or a
pincode returns None and the bot asks for a location pin instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.conversation.machine import Place
from app.data.reference import load_markets

_TAMIL = re.compile(r"[஀-௿]")


@dataclass(frozen=True)
class _Town:
    alias: str
    lat: float
    lon: float


class ReferenceGeocoder:
    def __init__(self, towns: list[_Town]) -> None:
        self._towns = sorted(towns, key=lambda t: -len(t.alias))  # longest name first

    @classmethod
    def from_reference(cls) -> ReferenceGeocoder:
        return cls([_Town(a, m.lat, m.lon) for m in load_markets() for a in m.aliases])

    def geocode(self, text: str) -> Place | None:
        t = " ".join(text.casefold().split())
        for town in self._towns:
            if _TAMIL.search(town.alias):
                found = town.alias in t
            else:
                found = (
                    re.search(r"(?<![a-z])" + re.escape(town.alias) + r"(?![a-z])", t) is not None
                )
            if found:
                name = town.alias if _TAMIL.search(town.alias) else town.alias.title()
                return Place(name, town.lat, town.lon)
        return None
