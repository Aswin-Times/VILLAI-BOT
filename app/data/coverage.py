"""Coverage report: which markets report which crops, and how often.

uv run python -m app.data.coverage                 # reads data/raw/datagov/history
uv run python -m app.data.coverage --write docs/coverage.md
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from app.data.csv_io import read_observations_csv
from app.data.normalize import is_uzhavar_sandhai
from app.data.sources.base import PriceObservation


@dataclass(frozen=True)
class CoverageRow:
    district: str
    market: str
    commodity: str
    days_reported: int
    last_reported: date
    retail: bool


def coverage_table(
    rows: Iterable[PriceObservation], today: date, window_days: int = 365
) -> list[CoverageRow]:
    start = today - timedelta(days=window_days)
    days: dict[tuple[str, str, str], set[date]] = defaultdict(set)
    for r in rows:
        if start <= r.obs_date <= today:
            days[(r.district, r.market, r.commodity)].add(r.obs_date)
    table = [
        CoverageRow(
            district=d,
            market=m,
            commodity=c,
            days_reported=len(ds),
            last_reported=max(ds),
            retail=is_uzhavar_sandhai(m),
        )
        for (d, m, c), ds in days.items()
    ]
    return sorted(table, key=lambda r: (r.commodity, -r.days_reported, r.market))


def render_markdown(table: Sequence[CoverageRow], today: date, window_days: int) -> str:
    lines = [
        f"# Coverage: days reported in the {window_days} days to {today.isoformat()}",
        "",
        "Retail = Uzhavar Sandhai (farmer-to-consumer, small lots). Never rank these for bulk.",
        "",
        "| District | Market | Commodity | Days reported | Last reported | Type |",
        "|---|---|---|---|---|---|",
    ]
    for r in table:
        kind = "retail" if r.retail else "wholesale"
        lines.append(
            f"| {r.district} | {r.market} | {r.commodity} | {r.days_reported} "
            f"| {r.last_reported.isoformat()} | {kind} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=Path("data/raw/datagov/history"))
    parser.add_argument("--window-days", type=int, default=365)
    parser.add_argument("--write", type=Path, default=None)
    args = parser.parse_args(argv)

    rows = [r for p in sorted(args.history.glob("*.csv")) for r in read_observations_csv(p)]
    today = date.today()
    md = render_markdown(coverage_table(rows, today, args.window_days), today, args.window_days)
    if args.write:
        args.write.write_text(md, encoding="utf-8")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
