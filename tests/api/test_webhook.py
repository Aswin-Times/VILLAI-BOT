"""The Twilio WhatsApp webhook, end to end: signed requests -> chat -> replies + DB."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.channels.base import ChannelError
from app.channels.twilio_whatsapp import twilio_signature
from app.config import Settings
from app.conversation.render import Renderer
from app.data.ingest import ingest_observations, sync_reference
from app.data.sources.base import PriceObservation
from app.main import create_app
from app.models import (
    Conversation,
    Farmer,
    FarmerCrop,
    InboundReceipt,
    MessageLog,
    Recommendation,
)

TODAY = date(2026, 11, 19)
TOKEN = "test-auth-token"
BASE_URL = "https://vilai.test"
PATH = "/webhooks/twilio/whatsapp"
PHONE = "+919876543210"
EN = Renderer("en")


class FakeChannel:
    name = "fake"

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    def send_text(self, to: str, body: str) -> None:
        if self.fail:
            raise ChannelError("down")
        self.sent.append((to, body))

    def bodies(self) -> list[str]:
        return [b for _, b in self.sent]


def settings(db_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": db_url,
        "phone_hash_secret": "test-hash-secret",
        "twilio_auth_token": TOKEN,
        "public_base_url": BASE_URL,
        "intent_provider": "rules",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def channel() -> FakeChannel:
    return FakeChannel()


@pytest.fixture
def make_client(engine: Engine, db_url: str) -> Callable[..., TestClient]:
    with Session(engine) as s:
        sync_reference(s)

    def _make(channel: FakeChannel, **overrides: Any) -> TestClient:
        app = create_app(settings(db_url, **overrides))
        app.state.channel = channel
        app.state.today = lambda: TODAY
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient], channel: FakeChannel) -> TestClient:
    return make_client(channel)


class Sender:
    """Builds signed Twilio webhook requests with unique message ids."""

    def __init__(self, client: TestClient, phone: str = PHONE) -> None:
        self.client, self.phone, self.n = client, phone, 0

    def __call__(self, body: str = "", sid: str | None = None, sign: bool = True, **extra: str):
        self.n += 1
        params = {
            "From": f"whatsapp:{self.phone}",
            "To": "whatsapp:+14155238886",
            "Body": body,
            "NumMedia": "0",
            "MessageSid": sid or f"SM{self.n:04d}",
            **extra,
        }
        headers = {"X-Twilio-Signature": twilio_signature(TOKEN, BASE_URL + PATH, params)}
        return self.client.post(PATH, data=params, headers=headers if sign else {})


def load_prices(engine: Engine, rows: Iterable[tuple[str, float]]) -> None:
    obs = [
        PriceObservation(
            obs_date=date(2026, 11, 18), state="Tamil Nadu", district="Dindigul", market=m,
            commodity="Tomato", variety="Deshi", grade="FAQ", min_price=modal - 150,
            max_price=modal + 150, modal_price=modal, source="test",
        )
        for m, modal in rows
    ]  # fmt: skip
    with Session(engine) as s:
        ingest_observations(s, obs)


def count(engine: Engine, model: type) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model)) or 0


# ---------- security ----------


def test_rejects_unsigned_requests(
    client: TestClient, channel: FakeChannel, engine: Engine
) -> None:
    resp = Sender(client)("hi", sign=False)

    assert resp.status_code == 403
    assert channel.sent == []
    assert count(engine, Conversation) == 0


def test_rejects_a_forged_signature(client: TestClient, channel: FakeChannel) -> None:
    params = {"From": f"whatsapp:{PHONE}", "Body": "hi", "MessageSid": "SM1", "NumMedia": "0"}

    resp = client.post(PATH, data=params, headers={"X-Twilio-Signature": "forged"})

    assert resp.status_code == 403
    assert channel.sent == []


def test_refuses_to_run_without_a_phone_hash_secret(
    make_client: Callable[..., TestClient], channel: FakeChannel
) -> None:
    client = make_client(channel, phone_hash_secret=None)

    assert Sender(client)("hi").status_code == 503
    assert channel.sent == []


# ---------- conversations ----------


def test_first_message_gets_the_welcome_and_stores_nothing_personal(
    client: TestClient, channel: FakeChannel, engine: Engine
) -> None:
    resp = Sender(client)("hi")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert channel.sent == [(PHONE, EN.render("welcome"))]
    with Session(engine) as s:
        conv = s.scalars(select(Conversation)).one()
        assert conv.farmer_id is None
        assert "9876543210" not in conv.phone_hash
    assert count(engine, Farmer) == 0
    assert count(engine, MessageLog) == 0


def test_whole_conversation_from_hello_to_advice(
    client: TestClient, channel: FakeChannel, engine: Engine
) -> None:
    load_prices(engine, [("Oddanchatram", 2450), ("Dindigul", 2300), ("Palani", 2380)])
    send = Sender(client)

    for body in ["hi", "2", "yes", "Dindigul", "tomato", "20 quintal thakkali", "1"]:
        assert send(body).status_code == 200

    advice = channel.bodies()[-2]
    assert advice.startswith("Tomato · 20 quintals · prices as of 18 Nov")
    assert "1. Oddanchatram" in advice
    assert channel.bodies()[-1] == EN.render("disclaimer")

    with Session(engine) as s:
        farmer = s.scalars(select(Farmer)).one()
        assert (farmer.phone_e164, farmer.language, farmer.place_name) == (PHONE, "en", "Dindigul")
        assert len(s.scalars(select(FarmerCrop)).all()) == 1
        rec = s.scalars(select(Recommendation)).one()
        assert rec.farmer_id == farmer.id
        inbound = [
            m.body
            for m in s.scalars(
                select(MessageLog).where(MessageLog.direction == "in").order_by(MessageLog.id)
            )
        ]
    # Logging starts with the consenting message; "hi" and "2" were never stored.
    assert inbound == ["yes", "Dindigul", "tomato", "20 quintal thakkali", "1"]


def test_a_retried_message_is_handled_once(
    client: TestClient, channel: FakeChannel, engine: Engine
) -> None:
    send = Sender(client)

    send("hi", sid="SMsame")
    send("hi", sid="SMsame")

    assert len(channel.sent) == 1
    assert count(engine, InboundReceipt) == 1


def test_declining_consent_deletes_the_conversation(
    client: TestClient, channel: FakeChannel, engine: Engine
) -> None:
    send = Sender(client)

    for body in ["hi", "2", "no"]:
        send(body)

    assert channel.bodies()[-1] == EN.render("consent_declined")
    assert count(engine, Conversation) == 0
    assert count(engine, Farmer) == 0


def test_two_farmers_are_kept_apart(client: TestClient, channel: FakeChannel) -> None:
    a, b = Sender(client, "+919800000001"), Sender(client, "+919800000002")

    a("hi")
    b("hi")
    a("2")

    assert channel.sent[-1] == ("+919800000001", EN.render("consent"))


def test_logs_show_only_masked_numbers(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    send = Sender(client)

    for body in ["hi", "2", "yes"]:
        send(body)

    assert "+91******3210" in caplog.text
    assert "9876543210" not in caplog.text


# ---------- failures ----------


def test_state_is_saved_even_if_sending_fails(
    make_client: Callable[..., TestClient], engine: Engine
) -> None:
    client = make_client(FakeChannel(fail=True))

    assert Sender(client)("hi").status_code == 200

    with Session(engine) as s:
        assert s.scalars(select(Conversation)).one().state == "lang"


def test_unexpected_errors_get_an_apology(
    client: TestClient, channel: FakeChannel, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr("app.conversation.service.handle", boom)

    assert Sender(client)("hi").status_code == 200
    assert channel.bodies() == [EN.render("error")]
