"""Load reference data and source observations into the database.

uv run python -m app.data.ingest --sync-reference data/raw/datagov/2026-11-18.csv
uv run python -m app.data.ingest data/raw/datagov/history     # every CSV in a folder
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.data.csv_io import read_observations_csv
from app.data.normalize import CommodityMatcher, MarketMatcher, is_uzhavar_sandhai, quality_flags
from app.data.reference import load_commodities, load_markets
from app.data.sources.base import PriceObservation
from app.db import make_engine
from app.models import ArrivalRow, Commodity, Market, PriceRow

# Need at least this many rows of a commodity on a day to judge outliers.
MIN_ROWS_FOR_REFERENCE = 3

PriceKey = tuple[date, int, int, str, str]


@dataclass
class IngestReport:
    inserted: int = 0
    updated: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    unknown_markets: dict[tuple[str, str], int] = field(default_factory=dict)


def sync_reference(session: Session) -> None:
    """Upsert markets and commodities from the seed files (the seed is the source of truth)."""
    markets = {m.code: m for m in session.scalars(select(Market))}
    for s in load_markets():
        m = markets.get(s.code) or Market(code=s.code)
        m.name, m.district, m.agmarknet_district = s.name, s.district, s.agmarknet_district
        m.lat, m.lon = s.lat, s.lon
        m.agmarknet_names = list(s.agmarknet_names)
        m.market_type, m.deductions_pct, m.verified = s.market_type, s.deductions_pct, s.verified
        session.add(m)

    commodities = {c.code: c for c in session.scalars(select(Commodity))}
    for sc in load_commodities():
        c = commodities.get(sc.code) or Commodity(code=sc.code)
        c.name_en, c.name_ta = sc.name_en, sc.name_ta
        c.agmarknet_commodity = sc.agmarknet_commodity
        c.agmarknet_varieties = list(sc.agmarknet_varieties)
        c.exclude_varieties = list(sc.exclude_varieties)
        c.synonyms = list(sc.synonyms)
        c.storable, c.storage_loss_pct_per_week = sc.storable, sc.storage_loss_pct_per_week
        c.pack_weights_kg = dict(sc.pack_weights_kg)
        c.mapping_verified = sc.mapping_verified
        session.add(c)
    session.commit()


def ingest_observations(session: Session, observations: Iterable[PriceObservation]) -> IngestReport:
    report = IngestReport()
    skipped: Counter[str] = Counter()
    unknown: Counter[tuple[str, str]] = Counter()
    market_ids = MarketMatcher(session.scalars(select(Market)))
    commodity_ids = CommodityMatcher(session.scalars(select(Commodity)))

    matched: list[tuple[PriceObservation, int, int]] = []
    for o in observations:
        if is_uzhavar_sandhai(o.market):
            skipped["retail"] += 1
            continue
        mid = market_ids.match(o.district, o.market)
        if mid is None:
            skipped["unknown_market"] += 1
            unknown[(o.district, o.market)] += 1
            continue
        cid = commodity_ids.match(o.commodity, o.variety)
        if cid is None:
            skipped["unknown_commodity"] += 1
            continue
        matched.append((o, mid, cid))

    if matched:
        _upsert_prices(session, matched, report)
        _upsert_arrivals(session, matched)
    session.commit()
    report.skipped = dict(skipped)
    report.unknown_markets = dict(unknown)
    return report


def _reference_modals(
    matched: Sequence[tuple[PriceObservation, int, int]],
) -> dict[tuple[int, date], float]:
    by_day: dict[tuple[int, date], list[float]] = defaultdict(list)
    for o, _mid, cid in matched:
        if o.modal_price is not None:
            by_day[(cid, o.obs_date)].append(o.modal_price)
    return {k: median(v) for k, v in by_day.items() if len(v) >= MIN_ROWS_FOR_REFERENCE}


def _upsert_prices(
    session: Session, matched: Sequence[tuple[PriceObservation, int, int]], report: IngestReport
) -> None:
    dates = [o.obs_date for o, _, _ in matched]
    commodity_ids = {cid for _, _, cid in matched}
    existing: dict[PriceKey, PriceRow] = {
        (r.obs_date, r.market_id, r.commodity_id, r.variety, r.grade): r
        for r in session.scalars(
            select(PriceRow).where(
                PriceRow.obs_date.between(min(dates), max(dates)),
                PriceRow.commodity_id.in_(commodity_ids),
            )
        )
    }
    references = _reference_modals(matched)
    for o, mid, cid in matched:
        key: PriceKey = (o.obs_date, mid, cid, o.variety, o.grade)
        flags = quality_flags(
            o.min_price, o.modal_price, o.max_price, references.get((cid, o.obs_date))
        )
        row = existing.get(key)
        if row is None:
            row = PriceRow(
                obs_date=o.obs_date,
                market_id=mid,
                commodity_id=cid,
                variety=o.variety,
                grade=o.grade,
            )
            session.add(row)
            existing[key] = row
            report.inserted += 1
        else:
            report.updated += 1
        row.min_price, row.modal_price, row.max_price = o.min_price, o.modal_price, o.max_price
        row.source, row.quality_flags = o.source, flags


def _upsert_arrivals(
    session: Session, matched: Sequence[tuple[PriceObservation, int, int]]
) -> None:
    totals: dict[tuple[date, int, int], float] = defaultdict(float)
    sources: dict[tuple[date, int, int], str] = {}
    for o, mid, cid in matched:
        if o.arrivals_tonnes is not None:
            totals[(o.obs_date, mid, cid)] += o.arrivals_tonnes
            sources[(o.obs_date, mid, cid)] = o.source
    for (day, mid, cid), tonnes in totals.items():
        row = session.scalars(
            select(ArrivalRow).where(
                ArrivalRow.obs_date == day,
                ArrivalRow.market_id == mid,
                ArrivalRow.commodity_id == cid,
            )
        ).one_or_none()
        if row is None:
            row = ArrivalRow(obs_date=day, market_id=mid, commodity_id=cid)
            session.add(row)
        row.arrivals_tonnes, row.source = tonnes, sources[(day, mid, cid)]


def _csv_files(paths: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.glob("*.csv")) if p.is_dir() else [p])
    return files


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--sync-reference", action="store_true")
    args = parser.parse_args(argv)

    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        if args.sync_reference:
            sync_reference(session)
            print("Reference data synced.")
        for path in _csv_files(args.paths):
            r = ingest_observations(session, read_observations_csv(path))
            print(f"{path}: +{r.inserted} new, {r.updated} updated, skipped {r.skipped}")
            for (district, market), n in sorted(r.unknown_markets.items(), key=lambda x: -x[1])[:5]:
                print(f"  unknown market: {district} / {market} ({n} rows)", file=sys.stderr)
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
