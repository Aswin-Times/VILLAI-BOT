"""API fixtures: an app wired to the test database with a fixed 'today'."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.deps import get_today
from app.config import Settings
from app.data.ingest import ingest_observations, sync_reference
from app.data.sources.base import PriceObservation
from app.main import create_app

TODAY = date(2026, 11, 19)


@pytest.fixture
def client(engine: Engine, db_url: str) -> TestClient:
    app = create_app(Settings(_env_file=None, database_url=db_url))
    app.dependency_overrides[get_today] = lambda: TODAY
    with Session(engine) as s:
        sync_reference(s)
    return TestClient(app)


@pytest.fixture
def load(engine: Engine) -> Callable[[Iterable[PriceObservation]], None]:
    def _load(observations: Iterable[PriceObservation]) -> None:
        with Session(engine) as s:
            ingest_observations(s, observations)

    return _load
