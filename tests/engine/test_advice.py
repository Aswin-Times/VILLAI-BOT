"""advise(): ranking + glut signals + warnings, all from in-memory inputs."""

from __future__ import annotations

from datetime import date, timedelta

from app.engine.advice import advise
from app.engine.ranking import MarketQuote
from app.engine.transport import Vehicle

TODAY = date(2026, 11, 19)
YESTERDAY = TODAY - timedelta(days=1)
FLEET = (Vehicle("tempo", 10, 14, 700), Vehicle("truck", 90, 35, 3000))


def quote(code: str, lat: float, modal: float, obs_date: date = YESTERDAY) -> MarketQuote:
    return MarketQuote(
        market_code=code,
        market_name=code.title(),
        lat=lat,
        lon=77.90,
        deductions_pct=0.08,
        obs_date=obs_date,
        min_price=modal - 100,
        modal_price=modal,
        max_price=modal + 100,
    )


def steady_then(today_value: float, day: date = YESTERDAY) -> dict[date, float]:
    h = {day - timedelta(days=i): 100.0 + (i % 3) for i in range(1, 29)}
    h[day] = today_value
    return h


def run(quotes: list[MarketQuote], arrivals: dict[str, dict[date, float]], top_n: int = 3):  # type: ignore[no-untyped-def]
    return advise(
        quotes,
        arrivals,
        qty_q=8,
        farmer_lat=10.40,
        farmer_lon=77.90,
        fleet=FLEET,
        today=TODAY,
        top_n=top_n,
    )


def test_glut_signal_for_each_option_on_its_data_date() -> None:
    quotes = [quote("a", 10.41, 2500), quote("b", 10.42, 2400)]

    a = run(quotes, {"a": steady_then(170), "b": steady_then(101)})

    assert a.gluts["a"].flagged
    assert a.gluts["a"].obs_date == YESTERDAY
    assert not a.gluts["b"].flagged


def test_regional_glut_counts_candidates_beyond_the_top_options() -> None:
    quotes = [quote("a", 10.41, 2500), quote("b", 10.42, 2400), quote("c", 10.43, 2300)]
    arrivals = {"a": steady_then(101), "b": steady_then(170), "c": steady_then(175)}

    a = run(quotes, arrivals, top_n=1)

    assert [o.quote.market_code for o in a.ranking.options] == ["a"]
    assert a.regional.flagged
    assert a.regional.spiking == ["b", "c"]


def test_markets_without_arrivals_data_get_no_glut_verdict() -> None:
    a = run([quote("a", 10.41, 2500)], {})

    assert a.gluts["a"].reason == "no_arrivals_today"
    assert not a.regional.flagged


def test_warns_when_there_is_no_recent_data() -> None:
    a = run([], {})

    assert a.warnings == ["no_recent_data"]


def test_warns_when_only_stale_data_is_available() -> None:
    a = run([quote("a", 10.41, 2500, obs_date=TODAY - timedelta(days=6))], {})

    assert a.ranking.best is None
    assert a.warnings == ["stale_data"]


def test_no_warnings_for_fresh_data() -> None:
    assert run([quote("a", 10.41, 2500)], {}).warnings == []
