"""The demo loader must never touch a real (non-SQLite) database."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.data.demo import demo_observations, main
from app.db import make_engine
from app.models import PriceRow


def test_refuses_non_sqlite_databases(capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://u:p@db/vilai")

    assert main([], settings=settings) == 2
    assert "SQLite" in capsys.readouterr().err


def test_every_demo_row_is_labelled_demo() -> None:
    rows = demo_observations(date(2026, 11, 18))

    assert rows
    assert {r.source for r in rows} == {"demo"}


def test_loads_demo_prices_into_a_fresh_sqlite_file(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'demo.db').as_posix()}"

    code = main(["--date", "2026-11-18"], settings=Settings(_env_file=None, database_url=url))

    assert code == 0
    engine = make_engine(url)
    with Session(engine) as s:
        sources = set(s.scalars(select(PriceRow.source)))
    engine.dispose()
    assert sources == {"demo"}
