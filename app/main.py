"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from app.api import advice, reference
from app.config import Settings
from app.db import make_engine, make_sessionmaker


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Vilai", version="0.1.0")
    app.state.sessionmaker = make_sessionmaker(make_engine(settings.database_url))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(advice.router)
    app.include_router(reference.router)
    return app


app = create_app()
