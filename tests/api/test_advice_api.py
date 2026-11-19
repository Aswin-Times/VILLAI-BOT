"""POST /v1/advice end to end: DB -> engine -> response + audit row."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.data.sources.base import PriceObservation
from app.models import Recommendation

Loader = Callable[[Iterable[PriceObservation]], None]
DAY = date(2026, 11, 18)
DINDIGUL_TOWN = {"lat": 10.37, "lon": 77.96}


def obs(
    market: str,
    modal: float,
    district: str = "Dindigul",
    commodity: str = "Tomato",
    variety: str = "Deshi",
    day: date = DAY,
    low: float | None = None,
    arrivals: float | None = None,
) -> PriceObservation:
    return PriceObservation(
        obs_date=day,
        state="Tamil Nadu",
        district=district,
        market=market,
        commodity=commodity,
        variety=variety,
        grade="FAQ",
        min_price=modal - 150 if low is None else low,
        max_price=modal + 150,
        modal_price=modal,
        arrivals_tonnes=arrivals,
        source="test",
    )


TOMATO_DAY = [
    obs("Oddanchatram", 2450),
    obs("Dindigul", 2300),
    obs("Palani", 2380),
]


def ask(client: TestClient, **overrides: Any) -> Any:
    body = {"commodity": "tomato", "quantity": 20, "unit": "quintal", **DINDIGUL_TOWN}
    body.update(overrides)
    return client.post("/v1/advice", json=body)


def test_ranks_mandis_by_take_home(client: TestClient, load: Loader) -> None:
    load(TOMATO_DAY)

    resp = ask(client)

    assert resp.status_code == 200
    data = resp.json()
    codes = [o["market_code"] for o in data["options"]]
    assert codes[0] == "oddanchatram"
    assert set(codes) == {"oddanchatram", "dindigul", "palani"}
    nets = [o["net_per_q"] for o in data["options"]]
    assert nets == sorted(nets, reverse=True)
    assert data["data_as_of"] == "2026-11-18"
    assert data["best_market_code"] == "oddanchatram"
    assert data["nearest_market_code"] == "dindigul"
    assert data["warnings"] == []


def test_numbers_are_consistent(client: TestClient, load: Loader) -> None:
    load(TOMATO_DAY)

    best = ask(client).json()["options"][0]

    assert best["modal_price"] == 2450
    assert best["deductions_per_q"] == round(2450 * 0.08, 2)
    expected_net = best["modal_price"] - best["deductions_per_q"] - best["transport_per_q"]
    assert abs(best["net_per_q"] - expected_net) < 0.02
    assert abs(best["total_net"] - best["net_per_q"] * 20) < 0.5
    assert best["net_per_q_low"] <= best["net_per_q"] <= best["net_per_q_high"]


def test_every_answer_is_logged_with_its_data_date(
    client: TestClient, load: Loader, engine: Engine
) -> None:
    load(TOMATO_DAY)

    rec_id = ask(client).json()["recommendation_id"]

    with Session(engine) as s:
        rec = s.get(Recommendation, rec_id)
        assert rec is not None
        assert rec.data_as_of == DAY
        assert rec.request["commodity"] == "tomato"
        assert rec.result["best_market_code"] == "oddanchatram"


def test_commodity_by_tamil_or_transliterated_name(client: TestClient, load: Loader) -> None:
    load(TOMATO_DAY)

    for name in ["thakkali", "தக்காளி", "Tomato"]:
        assert ask(client, commodity=name).json()["commodity_code"] == "tomato"


def test_quantity_in_kilograms(client: TestClient, load: Loader) -> None:
    load(TOMATO_DAY)

    assert ask(client, quantity=2000, unit="kg").json()["quantity_quintals"] == 20


def test_unknown_unit_is_a_422_with_a_reason(client: TestClient) -> None:
    resp = ask(client, unit="lorry")

    assert resp.status_code == 422
    assert "unit" in resp.json()["detail"]


def test_unknown_commodity_is_a_404(client: TestClient) -> None:
    assert ask(client, commodity="dragonfruit").status_code == 404


def test_flagged_rows_are_never_used(client: TestClient, load: Loader) -> None:
    load([obs("Oddanchatram", 2450, low=2900), obs("Dindigul", 2300)])  # min > modal

    codes = [o["market_code"] for o in ask(client).json()["options"]]

    assert codes == ["dindigul"]


def test_several_varieties_on_one_day_use_the_median(client: TestClient, load: Loader) -> None:
    load([obs("Oddanchatram", 2400, variety="Deshi"), obs("Oddanchatram", 2600, variety="Hybrid")])

    (only,) = ask(client).json()["options"]

    assert only["modal_price"] == 2500


def test_glut_warning_on_a_spiking_market(client: TestClient, load: Loader) -> None:
    history = [
        obs("Oddanchatram", 2450, day=DAY - timedelta(days=i), arrivals=100.0 + i % 3)
        for i in range(1, 29)
    ]
    load([*history, obs("Oddanchatram", 2450, arrivals=170.0)])

    best = ask(client).json()["options"][0]

    assert best["glut"]["flagged"] is True
    assert best["glut"]["arrivals_tonnes"] == 170
    assert round(best["glut"]["pct_above_normal"]) == 68


def test_no_data_says_so_instead_of_guessing(client: TestClient) -> None:
    data = ask(client).json()

    assert data["options"] == []
    assert data["best_market_code"] is None
    assert data["data_as_of"] is None
    assert data["warnings"] == ["no_recent_data"]


def test_unverified_crop_mapping_is_flagged(client: TestClient, load: Loader) -> None:
    load([obs("Oddanchatram", 4500, commodity="Onion", variety="Local")])

    data = ask(client, commodity="chinna vengayam").json()

    assert data["commodity_code"] == "small_onion"
    assert "commodity_mapping_unverified" in data["warnings"]


def test_rejects_locations_outside_india(client: TestClient) -> None:
    assert ask(client, lat=51.5, lon=-0.12).status_code == 422
