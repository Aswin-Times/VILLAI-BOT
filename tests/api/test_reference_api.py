"""Reference endpoints: markets, commodities, price history."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.data.reference import load_commodities, load_markets
from app.data.sources.base import PriceObservation

Loader = Callable[[Iterable[PriceObservation]], None]


def obs(day: date, modal: float) -> PriceObservation:
    return PriceObservation(
        obs_date=day,
        state="Tamil Nadu",
        district="Dindigul",
        market="Oddanchatram",
        commodity="Tomato",
        variety="Deshi",
        grade="FAQ",
        min_price=modal - 100,
        max_price=modal + 100,
        modal_price=modal,
        source="test",
    )


def test_lists_markets(client: TestClient) -> None:
    data = client.get("/v1/markets").json()

    assert len(data) == len(load_markets())
    odd = next(m for m in data if m["code"] == "oddanchatram")
    assert odd["district"] == "Dindigul"
    assert odd["verified"] is False


def test_lists_commodities_with_tamil_names(client: TestClient) -> None:
    data = client.get("/v1/commodities").json()

    assert len(data) == len(load_commodities())
    tomato = next(c for c in data if c["code"] == "tomato")
    assert tomato["name_ta"] == "தக்காளி"
    assert tomato["storable"] is False


def test_price_history_for_one_market(client: TestClient, load: Loader) -> None:
    today = date(2026, 11, 19)
    load([obs(today - timedelta(days=d), 2000 + d) for d in (40, 3, 1)])

    data = client.get(
        "/v1/prices", params={"commodity": "tomato", "market": "oddanchatram", "days": 30}
    ).json()

    assert [p["obs_date"] for p in data] == ["2026-11-16", "2026-11-18"]
    assert data[0]["modal_price"] == 2003


def test_price_history_unknown_commodity_is_404(client: TestClient) -> None:
    assert client.get("/v1/prices", params={"commodity": "kiwi"}).status_code == 404
