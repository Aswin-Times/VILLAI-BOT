"""FastAPI dependencies: a DB session per request, and today's date (overridable in tests)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.clock import today_ist


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.sessionmaker
    with factory() as session:
        yield session


def get_today() -> date:
    return today_ist()
