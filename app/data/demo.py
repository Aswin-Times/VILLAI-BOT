"""Load MADE-UP demo prices into a local SQLite database.

    DATABASE_URL=sqlite:///./vilai-demo.db uv run python -m app.data.demo

For trying the API (and building the bot) before real data is available.
These prices are invented and every row is tagged source="demo". The loader
refuses to run against anything but SQLite, so it can't reach a real database.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.clock import today_ist
from app.config import Settings
from app.data.ingest import ingest_observations, sync_reference
from app.data.sources.base import PriceObservation
from app.db import make_engine
from app.models import Base

# (district, market, commodity, variety, modal ₹/q) -- invented numbers.
_DEMO_PRICES = [
    ("Dindigul", "Oddanchatram", "Tomato", "Deshi", 2600),
    ("Dindigul", "Dindigul", "Tomato", "Deshi", 2450),
    ("Dindigul", "Palani", "Tomato", "Deshi", 2500),
    ("Coimbatore", "Coimbatore", "Tomato", "Hybrid", 2700),
    ("Dindigul", "Oddanchatram", "Onion", "Local", 4200),
    ("Dindigul", "Dindigul", "Onion", "Local", 4000),
    ("Perambalur", "Perambalur", "Onion", "Local", 4350),
    ("Erode", "Erode", "Turmeric", "Finger", 13500),
    ("Namakkal", "Namagiripettai", "Turmeric", "Finger", 13200),
    ("Thiruppur", "Udumalpettai RM", "Banana", "Poovan", 3200),
    ("Coimbatore", "Pollachi", "Banana", "Poovan", 3000),
    ("Coimbatore", "Mettupalayam", "Banana", "Poovan", 3100),
]


def _obs(
    day: date,
    district: str,
    market: str,
    commodity: str,
    variety: str,
    modal: float,
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
        min_price=round(modal * 0.9),
        max_price=round(modal * 1.1),
        modal_price=modal,
        arrivals_tonnes=arrivals,
        source="demo",
    )


def demo_observations(day: date) -> list[PriceObservation]:
    rows = [_obs(day, *p) for p in _DEMO_PRICES]
    # 28 days of steady tomato arrivals at Oddanchatram, then a spike on `day`,
    # so the glut warning has something to show.
    for i in range(1, 29):
        rows.append(
            _obs(
                day - timedelta(days=i),
                "Dindigul",
                "Oddanchatram",
                "Tomato",
                "Deshi",
                2650,
                arrivals=180.0 + (i % 4) * 5,
            )
        )
    rows[0] = _obs(day, "Dindigul", "Oddanchatram", "Tomato", "Deshi", 2600, arrivals=270.0)
    return rows


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)

    settings = settings or Settings()
    if not settings.database_url.startswith("sqlite"):
        print("Refusing: demo data only goes into a local SQLite database.", file=sys.stderr)
        return 2

    day = args.date or today_ist() - timedelta(days=1)
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        sync_reference(session)
        report = ingest_observations(session, demo_observations(day))
    engine.dispose()
    print(f"Loaded {report.inserted} new / {report.updated} updated DEMO rows for {day}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
