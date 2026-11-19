"""Process one inbound message: load the session, run the machine, save, reply.

Order matters: state is committed before replies are sent, so a failed send
never loses the farmer's progress. Phone numbers appear in logs only masked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session as Db

from app.channels.base import Channel, InboundMessage
from app.conversation.geocode import ReferenceGeocoder
from app.conversation.intents import IntentParser, ParsedIntent
from app.conversation.machine import Place, PriceQuote, handle
from app.conversation.render import Renderer
from app.conversation.rules_parser import RulesParser
from app.conversation.store import load_session, save_session
from app.data.reference import load_commodities
from app.engine.units import to_quintals
from app.models import InboundReceipt, MessageLog
from app.privacy import hash_phone, mask_phone
from app.schemas.advice import AdviceRequest, AdviceResponse
from app.services.advice import get_advice, latest_quotes, resolve_commodity

log = logging.getLogger("vilai.conversation")


@dataclass(frozen=True)
class ChatDeps:
    parser: IntentParser
    rules: RulesParser
    geocoder: ReferenceGeocoder
    phone_hash_secret: str
    today: date


class DbPorts:
    """The machine's ports, backed by the database and the engine."""

    def __init__(self, db: Db, deps: ChatDeps, farmer_id: int | None) -> None:
        self._db, self._deps, self._farmer_id = db, deps, farmer_id

    def parse(self, text: str) -> ParsedIntent:
        try:
            return self._deps.parser.parse(text)
        except Exception:  # the LLM parser can fail; rules always answer
            log.warning("intent parser %s failed; using rules", self._deps.parser.name)
            return self._deps.rules.parse(text)

    def crops_in(self, text: str) -> list[str]:
        return self._deps.rules.crops_in(text)

    def geocode(self, text: str) -> Place | None:
        return self._deps.geocoder.geocode(text)

    def to_quintals(self, commodity: str, quantity: float, unit: str) -> float:
        packs = next(c.pack_weights_kg for c in load_commodities() if c.code == commodity)
        return to_quintals(quantity, unit, packs)

    def advise(
        self, commodity: str, quantity: float, unit: str, lat: float, lon: float
    ) -> AdviceResponse:
        req = AdviceRequest(commodity=commodity, quantity=quantity, unit=unit, lat=lat, lon=lon)
        return get_advice(self._db, req, self._deps.today, farmer_id=self._farmer_id)

    def price(self, commodity: str, market: str) -> PriceQuote | None:
        c = resolve_commodity(self._db, commodity)
        if c is None:
            return None
        for q in latest_quotes(self._db, c.id, self._deps.today):
            if q.market_code == market and q.modal_price is not None:
                return PriceQuote(market, q.obs_date, q.min_price, q.modal_price, q.max_price)
        return None


def process_inbound(db: Db, msg: InboundMessage, channel: Channel, deps: ChatDeps) -> list[str]:
    who = mask_phone(msg.sender)
    if db.get(InboundReceipt, msg.message_id) is not None:
        log.info("duplicate message %s from %s ignored", msg.message_id, who)
        return []
    db.add(InboundReceipt(message_sid=msg.message_id))

    phone_hash = hash_phone(msg.sender, deps.phone_hash_secret)
    chat, farmer_id = load_session(db, phone_hash)
    try:
        new_chat, replies = handle(chat, msg, DbPorts(db, deps, farmer_id), deps.today)
    except Exception:
        log.exception("failed to handle %s message from %s", msg.kind, who)
        db.rollback()
        db.add(InboundReceipt(message_sid=msg.message_id))
        new_chat, replies = chat, [Renderer(chat.language or "en").render("error")]

    farmer = save_session(db, phone_hash, msg.sender, new_chat, datetime.now(UTC))
    if farmer is not None:
        db.add(
            MessageLog(
                farmer_id=farmer.id, direction="in", kind=msg.kind,
                body=msg.text, media_url=msg.media_url,
            )
        )  # fmt: skip
        db.add_all(
            MessageLog(farmer_id=farmer.id, direction="out", kind="text", body=r) for r in replies
        )
    db.commit()
    log.info("%s from %s: %s -> %s", msg.kind, who, chat.state, new_chat.state)

    for reply in replies:
        try:
            channel.send_text(msg.sender, reply)
        except Exception as e:
            log.error("sending to %s failed: %s", who, type(e).__name__)
    return replies
