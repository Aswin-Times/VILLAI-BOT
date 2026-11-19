"""The Alembic migrations and the SQLAlchemy models must describe one schema."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.db import make_engine
from app.models import Base, Commodity, Market, PriceRow

ROOT = Path(__file__).parents[2]


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_migrations_match_models(db_url: str) -> None:
    command.upgrade(alembic_config(db_url), "head")
    engine = make_engine(db_url)

    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    engine.dispose()
    assert diff == []


def test_migrations_downgrade_cleanly(db_url: str) -> None:
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "base")


def _market() -> Market:
    return Market(
        code="oddanchatram",
        name="Oddanchatram",
        district="Dindigul",
        agmarknet_district="Dindigul",
        lat=10.487,
        lon=77.748,
        agmarknet_names=["Oddanchatram"],
        market_type="wholesale",
        deductions_pct=0.08,
    )


def _commodity() -> Commodity:
    return Commodity(
        code="tomato",
        name_en="Tomato",
        name_ta="தக்காளி",
        agmarknet_commodity="Tomato",
        synonyms=["tomato", "தக்காளி"],
        storable=False,
    )


def test_one_price_row_per_market_crop_variety_grade_and_day(session: Session) -> None:
    market, commodity = _market(), _commodity()
    session.add_all([market, commodity])
    session.flush()

    def row() -> PriceRow:
        return PriceRow(
            obs_date=date(2026, 11, 18),
            market_id=market.id,
            commodity_id=commodity.id,
            variety="Deshi",
            grade="FAQ",
            modal_price=2200.0,
            source="datagov",
        )

    session.add(row())
    session.flush()
    session.add(row())
    with pytest.raises(IntegrityError):
        session.flush()


def test_tamil_text_and_lists_round_trip(session: Session) -> None:
    session.add(_commodity())
    session.commit()

    loaded = session.query(Commodity).one()

    assert loaded.name_ta == "தக்காளி"
    assert loaded.synonyms == ["tomato", "தக்காளி"]
