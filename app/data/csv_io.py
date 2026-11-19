"""Read and write `PriceObservation`s as CSV (raw daily dumps, backfill files)."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from app.data.sources.base import PriceObservation

COLUMNS = list(PriceObservation.model_fields)


def write_observations_csv(rows: Iterable[PriceObservation], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            data = row.model_dump(mode="json")
            writer.writerow({k: "" if v is None else v for k, v in data.items()})
            count += 1
    return count


def read_observations_csv(path: Path) -> list[PriceObservation]:
    with path.open(encoding="utf-8", newline="") as f:
        return [
            PriceObservation.model_validate({k: (v if v != "" else None) for k, v in row.items()})
            for row in csv.DictReader(f)
        ]
