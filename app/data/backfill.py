"""Download multi-year price history, one CSV per district x commodity.

    uv run python -m app.data.backfill            # last 5 years, pilot districts/crops
    uv run python -m app.data.backfill --years 3

Resumable: files that already exist are skipped, so re-run after a failure.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from app.config import Settings
from app.data.csv_io import write_observations_csv
from app.data.reference import load_markets, pilot_source_commodities
from app.data.sources.base import HistorySource
from app.data.sources.datagov import DataGovSource

DEFAULT_OUT = Path("data/raw")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def history_path(out_dir: Path, source_name: str, district: str, commodity: str) -> Path:
    return out_dir / source_name / "history" / f"{_slug(district)}__{_slug(commodity)}.csv"


def backfill(
    source: HistorySource,
    districts: Sequence[str],
    commodities: Sequence[str],
    out_dir: Path,
    since: date | None = None,
    state: str = "Tamil Nadu",
) -> list[Path]:
    paths: list[Path] = []
    for district in districts:
        for commodity in commodities:
            path = history_path(out_dir, source.name, district, commodity)
            paths.append(path)
            if path.exists():
                continue
            rows = source.fetch_history(district=district, commodity=commodity, state=state)
            if since is not None:
                rows = [r for r in rows if r.obs_date >= since]
            write_observations_csv(sorted(rows, key=lambda r: (r.obs_date, r.market)), path)
            print(f"{district} / {commodity}: {len(rows)} rows", file=sys.stderr)
    return paths


def years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 Feb in a non-leap target year
        return day.replace(year=day.year - years, day=28)


def pilot_districts() -> list[str]:
    return list(dict.fromkeys(m.agmarknet_district for m in load_markets()))


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    settings = settings or Settings()
    if settings.datagov_api_key is None:
        print("DATAGOV_API_KEY is not set. Add it to .env (see .env.example).", file=sys.stderr)
        return 2

    since = years_before(date.today(), args.years)
    source = DataGovSource(api_key=settings.datagov_api_key.get_secret_value())
    paths = backfill(source, pilot_districts(), pilot_source_commodities(), args.out, since)
    print(f"{len(paths)} files under {args.out / source.name / 'history'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
