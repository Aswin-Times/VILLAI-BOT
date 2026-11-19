"""Place names to coordinates, from the market towns in the seed."""

from __future__ import annotations

import pytest

from app.conversation.geocode import ReferenceGeocoder
from app.data.reference import load_markets

GEO = ReferenceGeocoder.from_reference()
DINDIGUL = next(m for m in load_markets() if m.code == "dindigul")


@pytest.mark.parametrize("text", ["Dindigul", "  dindigul ", "திண்டுக்கல்", "near Dindigul"])
def test_finds_a_town_in_any_spelling(text: str) -> None:
    place = GEO.geocode(text)

    assert place is not None
    assert (place.lat, place.lon) == (DINDIGUL.lat, DINDIGUL.lon)


def test_local_names_work() -> None:
    place = GEO.geocode("kovai")

    assert place is not None
    assert place.name == "Kovai"


def test_tamil_name_is_kept_for_display() -> None:
    place = GEO.geocode("திண்டுக்கல்")

    assert place is not None
    assert place.name == "திண்டுக்கல்"


@pytest.mark.parametrize("text", ["Atlantis", "", "624001"])
def test_unknown_places_return_none(text: str) -> None:
    assert GEO.geocode(text) is None
