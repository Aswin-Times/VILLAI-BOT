"""Health check endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_reports_ok() -> None:
    client = TestClient(create_app())

    resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
