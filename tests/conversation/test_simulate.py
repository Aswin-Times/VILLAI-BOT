"""The terminal simulator drives the real chat pipeline without Twilio."""

from __future__ import annotations

import io

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.conversation.render import Renderer
from app.conversation.simulate import main
from app.data.ingest import sync_reference


def test_scripted_chat_prints_the_bot_replies(engine: Engine, db_url: str) -> None:
    with Session(engine) as s:
        sync_reference(s)
    out = io.StringIO()

    code = main(
        ["--date", "2026-11-19"],
        settings=Settings(_env_file=None, database_url=db_url),
        stdin=io.StringIO("hi\n2\nyes\n/pin 10.36 77.97\ntomato\n"),
        stdout=out,
    )

    text = out.getvalue()
    assert code == 0
    assert Renderer("en").render("welcome") in text
    assert "Saved ✅ Crops: Tomato" in text
