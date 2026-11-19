"""Conversation state machine (plan §7).

    new -> lang -> consent -> location -> crops -> idle <-> confirm_query

`handle` is pure: it takes a session and one message and returns the new
session and the replies. Parsing, place lookup, unit conversion, advice and
prices come in through `Ports`, so the machine never touches the DB or the
network. Crop, quantity and place are always confirmed before advice.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from datetime import date
from typing import Any, Protocol

from app.channels.base import InboundMessage
from app.conversation.intents import ParsedIntent
from app.conversation.render import (
    Renderer,
    advice_message,
    crop_list,
    crop_name,
    fmt_date,
    fmt_quantity,
    inr,
    market_name,
)
from app.engine.units import UnitError
from app.schemas.advice import AdviceResponse

NEW, LANG, CONSENT, LOCATION, CROPS, IDLE, CONFIRM = (
    "new",
    "lang",
    "consent",
    "location",
    "crops",
    "idle",
    "confirm_query",
)
_TAMIL_CHOICES = {"1", "tamil", "தமிழ்", "ta", "thamizh"}
_ENGLISH_CHOICES = {"2", "english", "eng", "en", "ஆங்கிலம்"}


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class PriceQuote:
    market_code: str
    obs_date: date
    min_price: float | None
    modal_price: float
    max_price: float | None


class Ports(Protocol):
    def parse(self, text: str) -> ParsedIntent: ...
    def crops_in(self, text: str) -> list[str]: ...
    def geocode(self, text: str) -> Place | None: ...
    def to_quintals(self, commodity: str, quantity: float, unit: str) -> float: ...
    def advise(
        self, commodity: str, quantity: float, unit: str, lat: float, lon: float
    ) -> AdviceResponse: ...
    def price(self, commodity: str, market: str) -> PriceQuote | None: ...


@dataclass
class Session:
    state: str = NEW
    language: str | None = None
    consented: bool = False
    # Profile: collected only after consent.
    lat: float | None = None
    lon: float | None = None
    place: str | None = None
    crops: list[str] = field(default_factory=list)
    # The question being built: commodity, quantity, unit, quintals, place, lat, lon.
    pending: dict[str, Any] = field(default_factory=dict)
    last_disclaimer: str | None = None  # ISO date of the last disclaimer shown


def handle(
    session: Session, msg: InboundMessage, ports: Ports, today: date
) -> tuple[Session, list[str]]:
    s = copy.deepcopy(session)
    replies = _dispatch(s, msg, ports, today)
    return s, replies


def _dispatch(s: Session, msg: InboundMessage, ports: Ports, today: date) -> list[str]:
    r = Renderer(s.language or "en")
    text = (msg.text or "").strip()

    if s.state == NEW:
        s.state = LANG
        return [Renderer("en").render("welcome")]
    if msg.kind == "audio":
        return [r.render("audio_coming_soon")]
    if s.state == LANG:
        return _choose_language(s, text)
    if s.state == CONSENT:
        return _consent(s, ports.parse(text).intent if text else "unknown", r)
    if s.state == LOCATION or msg.kind == "location":
        return _location(s, msg, ports, r)
    if s.state == CROPS:
        return _crops(s, text, ports, r)
    if not text:
        return [r.render("unknown")]

    p = ports.parse(text)
    if s.state == CONFIRM:
        if p.intent == "yes":
            return _advise(s, ports, today, r)
        if p.intent == "no":
            s.state, s.pending = IDLE, {}
            return [r.render("change_what")]
    return _idle(s, p, ports, r)


def _choose_language(s: Session, text: str) -> list[str]:
    choice = text.casefold()
    if choice in _TAMIL_CHOICES:
        s.language = "ta"
    elif choice in _ENGLISH_CHOICES:
        s.language = "en"
    else:
        if s.consented:
            return [Renderer(s.language or "en").render("language_prompt")]
        return [Renderer("en").render("welcome")]
    r = Renderer(s.language)
    if s.consented:
        s.state = IDLE
        return [r.render("help")]
    s.state = CONSENT
    return [r.render("consent")]


def _consent(s: Session, intent: str, r: Renderer) -> list[str]:
    if intent == "yes":
        s.consented, s.state = True, LOCATION
        return [r.render("ask_location")]
    if intent == "no":
        reply = r.render("consent_declined")
        _forget(s)
        return [reply]
    return [r.render("consent")]


def _forget(s: Session) -> None:
    """Reset to a brand-new session, including the language choice."""
    blank = Session()
    for f in fields(Session):
        setattr(s, f.name, getattr(blank, f.name))


def _location(s: Session, msg: InboundMessage, ports: Ports, r: Renderer) -> list[str]:
    if msg.kind == "location" and msg.lat is not None and msg.lon is not None:
        s.lat, s.lon, s.place = msg.lat, msg.lon, None
    else:
        place = ports.geocode(msg.text or "") if msg.text else None
        if place is None:
            return [r.render("location_not_understood")]
        s.lat, s.lon, s.place = place.lat, place.lon, place.name
    if not s.crops:
        s.state = CROPS
        return [r.render("ask_crops", crop_list=crop_list(r.lang))]
    s.state = IDLE
    return [_onboarded(s, r)]


def _crops(s: Session, text: str, ports: Ports, r: Renderer) -> list[str]:
    found = ports.crops_in(text)
    if not found:
        return [r.render("crops_not_understood", crop_list=crop_list(r.lang))]
    s.crops, s.state = found, IDLE
    return [_onboarded(s, r)]


def _onboarded(s: Session, r: Renderer) -> str:
    crops = ", ".join(crop_name(c, r.lang) for c in s.crops)
    return r.render("onboarded", crops=crops, place=_place_label(s.place, r))


def _place_label(place: str | None, r: Renderer) -> str:
    return place or r.render("your_location")


def _idle(s: Session, p: ParsedIntent, ports: Ports, r: Renderer) -> list[str]:
    if p.intent == "advice":
        return _build_query(s, p, ports, r)
    if p.intent == "price":
        return _price(s, p, ports, r)
    if p.intent in ("help", "greeting"):
        return [r.render("help")]
    if p.intent in ("alert", "stop"):
        return [r.render("alerts_coming_soon")]
    if p.intent == "change_crops":
        s.state = CROPS
        return [r.render("ask_crops", crop_list=crop_list(r.lang))]
    if p.intent == "change_location":
        s.state = LOCATION
        return [r.render("ask_location")]
    if p.intent == "language":
        s.state = LANG
        return [r.render("language_prompt")]
    return [r.render("unknown")]


def _farmer_crop_list(s: Session, r: Renderer) -> str:
    if len(s.crops) > 1:
        return ", ".join(crop_name(c, r.lang) for c in s.crops)
    return crop_list(r.lang)


def _build_query(s: Session, p: ParsedIntent, ports: Ports, r: Renderer) -> list[str]:
    pending = dict(s.pending)
    if p.commodity:
        pending["commodity"] = p.commodity
    if p.quantity:
        pending["quantity"], pending["unit"] = p.quantity, p.unit or "quintal"
    if p.location_text and (place := ports.geocode(p.location_text)):
        pending.update(place=place.name, lat=place.lat, lon=place.lon)
    if "commodity" not in pending and len(s.crops) == 1:
        pending["commodity"] = s.crops[0]
    s.pending, s.state = pending, IDLE

    if "commodity" not in pending:
        return [r.render("ask_crop", crop_list=_farmer_crop_list(s, r))]
    crop = crop_name(pending["commodity"], r.lang)
    if "quantity" not in pending:
        return [r.render("ask_quantity", crop=crop)]
    try:
        quintals = ports.to_quintals(pending["commodity"], pending["quantity"], pending["unit"])
    except UnitError:
        for key in ("quantity", "unit", "quintals"):
            pending.pop(key, None)
        return [r.render("unit_not_understood")]
    pending["quintals"] = quintals
    s.state = CONFIRM
    label = _place_label(pending.get("place") or s.place, r)
    return [
        r.render("confirm_query", crop=crop, quantity=fmt_quantity(quintals, r.lang), place=label)
    ]


def _advise(s: Session, ports: Ports, today: date, r: Renderer) -> list[str]:
    q = s.pending
    lat: float | None = q.get("lat", s.lat)
    lon: float | None = q.get("lon", s.lon)
    if lat is None or lon is None:  # never advise without knowing where the farmer is
        s.state = LOCATION
        return [r.render("ask_location")]
    resp = ports.advise(q["commodity"], q["quantity"], q["unit"], lat, lon)
    replies = [advice_message(resp, r.lang, place=_place_label(q.get("place") or s.place, r))]
    if s.last_disclaimer != today.isoformat():
        replies.append(r.render("disclaimer"))
        s.last_disclaimer = today.isoformat()
    s.state, s.pending = IDLE, {}
    return replies


def _price(s: Session, p: ParsedIntent, ports: Ports, r: Renderer) -> list[str]:
    commodity = p.commodity or (s.crops[0] if len(s.crops) == 1 else None)
    if commodity is None:
        return [r.render("ask_crop", crop_list=_farmer_crop_list(s, r))]
    crop = crop_name(commodity, r.lang)
    if p.market is None:
        return [r.render("price_which_market", crop=crop)]
    market = market_name(p.market, r.lang)
    quote = ports.price(commodity, p.market)
    if quote is None:
        return [r.render("price_no_data", crop=crop, market=market)]
    return [
        r.render(
            "price",
            crop=crop,
            market=market,
            modal=inr(quote.modal_price),
            low=inr(_or(quote.min_price, quote.modal_price)),
            high=inr(_or(quote.max_price, quote.modal_price)),
            date=fmt_date(quote.obs_date, r.lang),
        )
    ]


def _or(value: float | None, default: float) -> float:
    return default if value is None else value
