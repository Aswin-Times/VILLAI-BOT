"""Database engine and session helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str) -> Engine:
    engine = create_engine(url)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
