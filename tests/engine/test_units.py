"""Quantities from farmers arrive in many units; the engine works in quintals."""

from __future__ import annotations

import pytest

from app.engine.units import UnitError, to_quintals


@pytest.mark.parametrize("unit", ["quintal", "quintals", "q", "qtl", "Quintal", " QTL "])
def test_quintal_spellings(unit: str) -> None:
    assert to_quintals(20, unit) == 20


def test_kilograms() -> None:
    assert to_quintals(500, "kg") == 5


@pytest.mark.parametrize("unit", ["tonne", "tonnes", "ton", "t"])
def test_tonnes(unit: str) -> None:
    assert to_quintals(2, unit) == 20


def test_bags_use_the_crop_bag_weight() -> None:
    assert to_quintals(10, "bag", pack_weights_kg={"bag": 50}) == 5


def test_crates_without_a_known_weight_need_asking() -> None:
    with pytest.raises(UnitError, match="crate"):
        to_quintals(10, "crate", pack_weights_kg={"bag": 50})


def test_unknown_unit_is_rejected() -> None:
    with pytest.raises(UnitError):
        to_quintals(3, "lorry")


@pytest.mark.parametrize("qty", [0, -5])
def test_quantity_must_be_positive(qty: float) -> None:
    with pytest.raises(UnitError):
        to_quintals(qty, "kg")
