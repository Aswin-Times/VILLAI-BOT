"""Tests for the data.gov.in (OGD, Agmarknet-backed) price source adapter."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.data.sources.base import DataSourceError, PriceObservation, SchemaDriftError
from app.data.sources.datagov import DataGovSource

FIXTURE = Path(__file__).parents[1] / "fixtures" / "datagov" / "variety_tomato_tn_2026-11-18.json"
FAKE_KEY = "test-key-not-real"


def load_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def paged_handler(payload: dict[str, Any], seen: list[httpx.Request]) -> Any:
    """Serve `payload["records"]` in pages according to the request's offset/limit."""
    records = payload["records"]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        page = dict(payload, total=len(records), records=records[offset : offset + limit])
        return httpx.Response(200, json=page)

    return handler


def make_source(handler: Any, **kwargs: Any) -> DataGovSource:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return DataGovSource(api_key=FAKE_KEY, client=client, sleep=lambda _s: None, **kwargs)


def test_parses_real_record_into_price_observation() -> None:
    seen: list[httpx.Request] = []
    source = make_source(paged_handler(load_fixture(), seen))

    obs = source.fetch(day=date(2026, 11, 18), commodities=["Tomato"])

    first = obs[0]
    assert first == PriceObservation(
        obs_date=date(2026, 11, 18),
        state="Tamil Nadu",
        district="Thiruchirappalli",
        market="Manapparai(Uzhavar Sandhai )",
        commodity="Tomato",
        variety="Other",
        grade="Local",
        min_price=3000.0,
        max_price=3000.0,
        modal_price=3000.0,
        arrivals_tonnes=None,
        source="datagov",
    )


def test_follows_pages_until_total_is_reached() -> None:
    seen: list[httpx.Request] = []
    source = make_source(paged_handler(load_fixture(), seen), page_size=4)

    obs = source.fetch(day=date(2026, 11, 18), commodities=["Tomato"])

    assert len(obs) == 10
    assert [int(r.url.params["offset"]) for r in seen] == [0, 4, 8]


def test_advances_by_rows_returned_when_server_caps_page_size() -> None:
    """The public sample key returns at most 10 rows whatever `limit` asks for."""
    payload = load_fixture()
    records = payload["records"]
    seen: list[httpx.Request] = []

    def capped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        offset = int(request.url.params["offset"])
        page = dict(payload, total=len(records), records=records[offset : offset + 3])
        return httpx.Response(200, json=page)

    source = make_source(capped, page_size=1000)

    obs = source.fetch(day=date(2026, 11, 18), commodities=["Tomato"])

    assert len(obs) == 10
    assert [int(r.url.params["offset"]) for r in seen] == [0, 3, 6, 9]


def test_sends_state_commodity_and_date_filters() -> None:
    seen: list[httpx.Request] = []
    source = make_source(paged_handler(load_fixture(), seen))

    source.fetch(day=date(2026, 11, 18), commodities=["Tomato"], state="Tamil Nadu")

    params = seen[0].url.params
    assert params["filters[State]"] == "Tamil Nadu"
    assert params["filters[Commodity]"] == "Tomato"
    assert params["filters[Arrival_Date]"] == "18/11/2026"
    assert params["format"] == "json"


def test_history_filters_by_district_and_commodity_across_all_dates() -> None:
    seen: list[httpx.Request] = []
    source = make_source(paged_handler(load_fixture(), seen), page_size=4)

    obs = source.fetch_history(district="Dindigul", commodity="Tomato")

    assert len(obs) == 10
    params = seen[0].url.params
    assert params["filters[State]"] == "Tamil Nadu"
    assert params["filters[District]"] == "Dindigul"
    assert params["filters[Commodity]"] == "Tomato"
    assert "filters[Arrival_Date]" not in params


def test_fetches_each_commodity_separately() -> None:
    seen: list[httpx.Request] = []
    source = make_source(paged_handler(load_fixture(), seen))

    source.fetch(day=date(2026, 11, 18), commodities=["Tomato", "Onion"])

    assert [r.url.params["filters[Commodity]"] for r in seen] == ["Tomato", "Onion"]


def test_blank_price_becomes_none() -> None:
    payload = load_fixture()
    payload["records"] = [dict(payload["records"][0], Min_Price="", Max_Price="NR")]
    source = make_source(paged_handler(payload, []))

    (obs,) = source.fetch(day=date(2026, 11, 18), commodities=["Tomato"])

    assert obs.min_price is None
    assert obs.max_price is None
    assert obs.modal_price == 3000.0


def test_missing_field_raises_schema_drift() -> None:
    payload = load_fixture()
    payload["field"] = [f for f in payload["field"] if f["id"] != "Modal_Price"]
    source = make_source(paged_handler(payload, []))

    with pytest.raises(SchemaDriftError, match="Modal_Price"):
        source.fetch(day=date(2026, 11, 18), commodities=["Tomato"])


def test_retries_timeouts_then_succeeds() -> None:
    calls = {"n": 0}
    good = paged_handler(load_fixture(), [])

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise httpx.ReadTimeout("slow", request=request)
        response: httpx.Response = good(request)
        return response

    source = make_source(flaky, max_attempts=3)

    obs = source.fetch(day=date(2026, 11, 18), commodities=["Tomato"])

    assert len(obs) == 10
    assert calls["n"] == 3


def test_backs_off_and_retries_when_rate_limited() -> None:
    calls = {"n": 0}
    waits: list[float] = []
    good = paged_handler(load_fixture(), [])

    def limited(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        response: httpx.Response = good(request)
        return response

    client = httpx.Client(transport=httpx.MockTransport(limited))
    source = DataGovSource(api_key=FAKE_KEY, client=client, sleep=waits.append)

    obs = source.fetch(day=date(2026, 11, 18), commodities=["Tomato"])

    assert len(obs) == 10
    assert len(waits) == 1
    assert waits[0] > 0


def test_gives_up_after_max_attempts() -> None:
    def always_slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    source = make_source(always_slow, max_attempts=2)

    with pytest.raises(DataSourceError):
        source.fetch(day=date(2026, 11, 18), commodities=["Tomato"])


def test_http_error_does_not_leak_api_key() -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "Key not authorised"})

    source = make_source(forbidden)

    with pytest.raises(DataSourceError) as exc:
        source.fetch(day=date(2026, 11, 18), commodities=["Tomato"])

    assert "403" in str(exc.value)
    assert FAKE_KEY not in str(exc.value)
