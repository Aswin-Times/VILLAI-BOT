"""Tests for the resumable history backfill (district x commodity files)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.data.backfill import backfill, years_before
from app.data.csv_io import read_observations_csv
from app.data.sources.base import PriceObservation


def obs(day: date, district: str = "Dindigul", commodity: str = "Tomato") -> PriceObservation:
    return PriceObservation(
        obs_date=day,
        state="Tamil Nadu",
        district=district,
        market="Oddanchatram",
        commodity=commodity,
        variety="Deshi",
        grade="FAQ",
        min_price=1800.0,
        max_price=2600.0,
        modal_price=2200.0,
        source="fake",
    )


class FakeHistorySource:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def fetch_history(
        self, *, district: str, commodity: str, state: str = "Tamil Nadu"
    ) -> list[PriceObservation]:
        self.calls.append((district, commodity))
        return [
            obs(date(2019, 1, 1), district, commodity),
            obs(date(2024, 6, 1), district, commodity),
        ]


def test_writes_one_file_per_district_and_commodity(tmp_path: Path) -> None:
    source = FakeHistorySource()

    paths = backfill(source, ["Dindigul", "Thiruppur"], ["Tomato", "Banana - Green"], tmp_path)

    assert len(paths) == 4
    assert tmp_path / "fake" / "history" / "thiruppur__banana-green.csv" in paths
    assert all(p.exists() for p in paths)


def test_drops_rows_older_than_since(tmp_path: Path) -> None:
    source = FakeHistorySource()

    (path,) = backfill(source, ["Dindigul"], ["Tomato"], tmp_path, since=date(2021, 11, 1))

    assert [r.obs_date for r in read_observations_csv(path)] == [date(2024, 6, 1)]


def test_years_before_handles_leap_day() -> None:
    assert years_before(date(2028, 2, 29), 5) == date(2023, 2, 28)
    assert years_before(date(2026, 11, 19), 5) == date(2021, 11, 19)


def test_skips_files_already_downloaded(tmp_path: Path) -> None:
    backfill(FakeHistorySource(), ["Dindigul"], ["Tomato"], tmp_path)
    second = FakeHistorySource()

    backfill(second, ["Dindigul", "Erode"], ["Tomato"], tmp_path)

    assert second.calls == [("Erode", "Tomato")]
