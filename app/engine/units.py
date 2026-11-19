"""Convert farmer quantities to quintals (1 quintal = 100 kg)."""

from __future__ import annotations

from collections.abc import Mapping


class UnitError(ValueError):
    """The quantity or unit can't be converted; the bot should ask the farmer."""


_PER_QUINTAL = {
    "quintal": 1.0,
    "quintals": 1.0,
    "q": 1.0,
    "qtl": 1.0,
    "kg": 0.01,
    "kgs": 0.01,
    "kilo": 0.01,
    "kilos": 0.01,
    "tonne": 10.0,
    "tonnes": 10.0,
    "ton": 10.0,
    "tons": 10.0,
    "t": 10.0,
}
_PACKS = {"bag": "bag", "bags": "bag", "crate": "crate", "crates": "crate"}


def to_quintals(
    quantity: float, unit: str, pack_weights_kg: Mapping[str, float] | None = None
) -> float:
    if quantity <= 0:
        raise UnitError("quantity must be positive")
    u = unit.strip().lower()
    if u in _PER_QUINTAL:
        return quantity * _PER_QUINTAL[u]
    if u in _PACKS:
        pack = _PACKS[u]
        weight = (pack_weights_kg or {}).get(pack)
        if weight is None:
            raise UnitError(f"weight of one {pack} is not known for this crop")
        return quantity * weight / 100
    raise UnitError(f"unknown unit: {unit!r}")
