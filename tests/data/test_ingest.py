"""Loading reference data and source observations into the database."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.data.csv_io import write_observations_csv
from app.data.ingest import ingest_observations, main, sync_reference
from app.data.reference import load_commodities, load_markets
from app.data.sources.base import PriceObservation
from app.models import ArrivalRow, Commodity, Market, PriceRow

DAY = date(2026, 11, 18)


def obs(
    market: str = "Oddanchatram",
    district: str = "Dindigul",
    commodity: str = "Tomato",
    variety: str = "Deshi",
    modal: float | None = 2200.0,
    low: float | None = 1800.0,
    high: float | None = 2600.0,
    arrivals: float | None = None,
    day: date = DAY,
) -> PriceObservation:
    return PriceObservation(
        obs_date=day,
        state="Tamil Nadu",
        district=district,
        market=market,
        commodity=commodity,
        variety=variety,
        grade="FAQ",
        min_price=low,
        max_price=high,
        modal_price=modal,
        arrivals_tonnes=arrivals,
        source="datagov",
    )


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_sync_reference_loads_seed_markets_and_commodities(session: Session) -> None:
    sync_reference(session)

    assert count(session, Market) == len(load_markets())
    assert count(session, Commodity) == len(load_commodities())
    odd = session.scalars(select(Market).where(Market.code == "oddanchatram")).one()
    assert "Oddunchairum" in odd.agmarknet_names


def test_sync_reference_is_idempotent_and_updates_in_place(session: Session) -> None:
    sync_reference(session)
    odd = session.scalars(select(Market).where(Market.code == "oddanchatram")).one()
    odd.deductions_pct = 0.5
    session.commit()

    sync_reference(session)

    assert count(session, Market) == len(load_markets())
    session.refresh(odd)
    assert odd.deductions_pct == 0.08


def test_ingests_matching_rows(session: Session) -> None:
    sync_reference(session)

    report = ingest_observations(session, [obs()])

    row = session.scalars(select(PriceRow)).one()
    assert (row.obs_date, row.variety, row.modal_price, row.quality_flags) == (
        DAY,
        "Deshi",
        2200.0,
        [],
    )
    assert report.inserted == 1


def test_reingesting_updates_instead_of_duplicating(session: Session) -> None:
    sync_reference(session)
    ingest_observations(session, [obs(modal=2200.0)])

    report = ingest_observations(session, [obs(modal=2300.0)])

    assert count(session, PriceRow) == 1
    assert session.scalars(select(PriceRow)).one().modal_price == 2300.0
    assert (report.inserted, report.updated) == (0, 1)


def test_skips_retail_unknown_market_and_unknown_commodity(session: Session) -> None:
    sync_reference(session)

    report = ingest_observations(
        session,
        [
            obs(market="Palani(Uzhavar Sandhai )"),
            obs(market="Nowhere Mandi"),
            obs(market="Nowhere Mandi"),
            obs(commodity="Brinjal"),
        ],
    )

    assert count(session, PriceRow) == 0
    assert report.skipped == {"retail": 1, "unknown_market": 2, "unknown_commodity": 1}
    assert report.unknown_markets == {("Dindigul", "Nowhere Mandi"): 2}


def test_bad_rows_are_kept_with_flags(session: Session) -> None:
    sync_reference(session)

    ingest_observations(session, [obs(low=2500.0, modal=2200.0, high=2600.0)])

    assert session.scalars(select(PriceRow)).one().quality_flags == ["price_order"]


def test_outliers_are_flagged_against_the_days_typical_price(session: Session) -> None:
    sync_reference(session)
    normal = [
        obs(market=m, district=d, modal=2200.0)
        for m, d in [("Oddanchatram", "Dindigul"), ("Dindigul", "Dindigul"), ("Palani", "Dindigul")]
    ]
    wild = obs(market="Coimbatore", district="Coimbatore", low=9000, modal=9500, high=9900)

    ingest_observations(session, [*normal, wild])

    flags = {r.market_id: r.quality_flags for r in session.scalars(select(PriceRow)).all()}
    coimbatore = session.scalars(select(Market).where(Market.code == "coimbatore")).one()
    assert flags[coimbatore.id] == ["outlier"]
    assert sum(1 for f in flags.values() if f == []) == 3


def test_command_line_loads_csv_folders(
    engine: Engine, db_url: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "history"
    write_observations_csv([obs(), obs(market="Nowhere Mandi")], folder / "dindigul__tomato.csv")

    code = main(
        [str(folder), "--sync-reference"], settings=Settings(_env_file=None, database_url=db_url)
    )

    assert code == 0
    with Session(engine) as s:
        assert count(s, PriceRow) == 1
    assert "Nowhere Mandi" in capsys.readouterr().err


def test_arrivals_are_summed_across_varieties(session: Session) -> None:
    sync_reference(session)

    ingest_observations(
        session,
        [obs(variety="Deshi", arrivals=40.0), obs(variety="Hybrid", arrivals=25.5)],
    )

    arrival = session.scalars(select(ArrivalRow)).one()
    assert arrival.arrivals_tonnes == 65.5
    assert arrival.obs_date == DAY
