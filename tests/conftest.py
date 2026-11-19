"""Shared fixtures.

Tests run on a throwaway SQLite file by default. Set TEST_DATABASE_URL to a
Postgres URL (CI does) to run the same tests against Postgres; its public
schema is wiped before each test that uses the database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import make_engine
from app.models import Base


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")
    engine.dispose()
    return url


@pytest.fixture
def engine(db_url: str) -> Iterator[Engine]:
    eng = make_engine(db_url)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s
