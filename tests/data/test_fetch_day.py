"""Tests for the daily fetch job that saves one day of observations to CSV."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.config import Settings
from app.data.csv_io import read_observations_csv, write_observations_csv
from app.data.fetch_day import fetch_day, main, yesterday_ist
from app.data.sources.base import PriceObservation


def obs(**overrides: object) -> PriceObservation:
    base: dict[str, object] = {
        "obs_date": date(2026, 11, 18),
        "state": "Tamil Nadu",
        "district": "Dindigul",
        "market": "Oddanchatram",
        "commodity": "Tomato",
        "variety": "Deshi",
        "grade": "FAQ",
        "min_price": 1800.0,
        "max_price": 2600.0,
        "modal_price": 2200.0,
        "arrivals_tonnes": 120.5,
        "source": "fake",
    }
    base.update(overrides)
    return PriceObservation.model_validate(base)


class FakeSource:
    name = "fake"

    def __init__(self, rows: list[PriceObservation]) -> None:
        self.rows = rows
        self.calls: list[tuple[date, list[str], str]] = []

    def fetch(
        self, *, day: date, commodities: Sequence[str], state: str = "Tamil Nadu"
    ) -> list[PriceObservation]:
        self.calls.append((day, list(commodities), state))
        return self.rows


def test_csv_round_trip_keeps_values_and_missing_prices(tmp_path: Path) -> None:
    rows = [obs(), obs(market="Palani", min_price=None, arrivals_tonnes=None)]
    path = tmp_path / "out.csv"

    written = write_observations_csv(rows, path)

    assert written == 2
    assert read_observations_csv(path) == rows


def test_fetch_day_saves_one_file_per_source_and_date(tmp_path: Path) -> None:
    source = FakeSource([obs()])

    path = fetch_day(source, date(2026, 11, 18), ["Tomato", "Onion"], tmp_path)

    assert path == tmp_path / "fake" / "2026-11-18.csv"
    assert read_observations_csv(path) == [obs()]
    assert source.calls == [(date(2026, 11, 18), ["Tomato", "Onion"], "Tamil Nadu")]


def test_yesterday_uses_india_time_not_utc() -> None:
    # 20:00 UTC on 19 Nov is 01:30 IST on 20 Nov, so "yesterday" is 19 Nov.
    now = datetime(2026, 11, 19, 20, 0, tzinfo=UTC)

    assert yesterday_ist(now) == date(2026, 11, 19)


def test_main_refuses_to_run_without_api_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--out", str(tmp_path)], settings=Settings(_env_file=None, datagov_api_key=None))

    assert code == 2
    assert "DATAGOV_API_KEY" in capsys.readouterr().err
