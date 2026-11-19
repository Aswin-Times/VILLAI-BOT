"""Fetch one day of mandi prices and save them as CSV.

uv run python -m app.data.fetch_day                # yesterday (India time)
uv run python -m app.data.fetch_day --date 2026-11-18
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path

from app.clock import IST
from app.config import Settings
from app.data.csv_io import write_observations_csv
from app.data.reference import pilot_source_commodities
from app.data.sources.base import PriceSource
from app.data.sources.datagov import DataGovSource

DEFAULT_OUT = Path("data/raw")


def yesterday_ist(now: datetime | None = None) -> date:
    now = now or datetime.now(IST)
    return now.astimezone(IST).date() - timedelta(days=1)


def fetch_day(
    source: PriceSource,
    day: date,
    commodities: Sequence[str],
    out_dir: Path,
    state: str = "Tamil Nadu",
) -> Path:
    rows = source.fetch(day=day, commodities=commodities, state=state)
    path = out_dir / source.name / f"{day.isoformat()}.csv"
    write_observations_csv(rows, path)
    return path


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--commodity", action="append", dest="commodities")
    args = parser.parse_args(argv)

    settings = settings or Settings()
    if settings.datagov_api_key is None:
        print("DATAGOV_API_KEY is not set. Add it to .env (see .env.example).", file=sys.stderr)
        return 2

    day = args.date or yesterday_ist()
    commodities = args.commodities or pilot_source_commodities()
    source = DataGovSource(api_key=settings.datagov_api_key.get_secret_value())
    path = fetch_day(source, day, commodities, args.out)
    print(f"Saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
