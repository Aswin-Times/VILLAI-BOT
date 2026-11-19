"""Conversation state machine, driven by scripted message sequences (plan §10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.channels.base import InboundMessage
from app.conversation.machine import Place, PriceQuote, Session, handle
from app.conversation.render import Renderer, advice_message
from app.conversation.rules_parser import RulesParser
from app.engine.units import to_quintals
from app.schemas.advice import AdviceResponse
from tests.conversation.factories import advice_response

TODAY = date(2026, 11, 19)
PARSER = RulesParser.from_reference()
PLACES = {
    "dindigul": Place("Dindigul", 10.3624, 77.9695),
    "திண்டுக்கல்": Place("திண்டுக்கல்", 10.3624, 77.9695),
    "palani": Place("Palani", 10.45, 77.5161),
}
PACKS = {"tomato": {"crate": 25.0}, "turmeric": {"bag": 70.0}, "small_onion": {"bag": 50.0}}


@dataclass
class FakePorts:
    advice: AdviceResponse = field(default_factory=advice_response)
    prices: dict[tuple[str, str], PriceQuote] = field(default_factory=dict)
    advise_calls: list[dict[str, Any]] = field(default_factory=list)

    def parse(self, text: str) -> Any:
        return PARSER.parse(text)

    def crops_in(self, text: str) -> list[str]:
        return PARSER.crops_in(text)

    def geocode(self, text: str) -> Place | None:
        return PLACES.get(text.strip().casefold())

    def to_quintals(self, commodity: str, quantity: float, unit: str) -> float:
        return to_quintals(quantity, unit, PACKS.get(commodity, {}))

    def advise(self, commodity: str, quantity: float, unit: str, lat: float, lon: float) -> Any:
        self.advise_calls.append(
            {"commodity": commodity, "quantity": quantity, "unit": unit, "lat": lat, "lon": lon}
        )
        return self.advice

    def price(self, commodity: str, market: str) -> PriceQuote | None:
        return self.prices.get((commodity, market))


def text(body: str) -> InboundMessage:
    return InboundMessage(
        channel="test", message_id="m", sender="+919876543210", kind="text", text=body
    )


def pin(lat: float, lon: float) -> InboundMessage:
    return InboundMessage(
        channel="test", message_id="m", sender="+919876543210", kind="location", lat=lat, lon=lon
    )


def run(
    messages: list[InboundMessage | str], session: Session | None = None, ports: Any = None
) -> tuple[Session, list[list[str]]]:
    session = session or Session()
    ports = ports or FakePorts()
    replies = []
    for m in messages:
        msg = text(m) if isinstance(m, str) else m
        session, out = handle(session, msg, ports, TODAY)
        replies.append(out)
    return session, replies


def onboarded(language: str = "en", crops: list[str] | None = None) -> Session:
    return Session(
        state="idle",
        language=language,
        consented=True,
        lat=10.3624,
        lon=77.9695,
        place="Dindigul",
        crops=crops if crops is not None else ["tomato", "turmeric"],
    )


EN, TA = Renderer("en"), Renderer("ta")


# ---------- onboarding ----------


def test_full_onboarding_in_tamil() -> None:
    s, replies = run(["vanakkam", "1", "ஆம்", "திண்டுக்கல்", "தக்காளி, மஞ்சள்"])

    assert replies[0] == [EN.render("welcome")]
    assert replies[1] == [TA.render("consent")]
    assert replies[2] == [TA.render("ask_location")]
    assert replies[3][0] == TA.render("ask_crops", crop_list="தக்காளி, சின்ன வெங்காயம், மஞ்சள், வாழை")
    assert "தக்காளி, மஞ்சள்" in replies[4][0]
    assert (s.state, s.language, s.consented, s.crops) == (
        "idle",
        "ta",
        True,
        ["tomato", "turmeric"],
    )
    assert (s.lat, s.lon, s.place) == (10.3624, 77.9695, "திண்டுக்கல்")


def test_onboarding_in_english_with_a_location_pin() -> None:
    s, replies = run(["hi", "2", "YES", pin(10.40, 77.90), "tomato"])

    assert replies[1] == [EN.render("consent")]
    assert (s.lat, s.lon, s.crops, s.language) == (10.40, 77.90, ["tomato"], "en")


def test_nothing_about_the_farmer_is_held_before_consent() -> None:
    s, _ = run(["hi", "2"])

    assert s.state == "consent"
    assert not s.consented
    assert (s.lat, s.lon, s.place, s.crops, s.pending) == (None, None, None, [], {})


def test_declining_consent_forgets_everything() -> None:
    s, replies = run(["hi", "2", "no"])

    assert replies[2] == [EN.render("consent_declined")]
    assert s == Session()


def test_unclear_language_choice_repeats_the_welcome() -> None:
    s, replies = run(["hi", "french"])

    assert replies[1] == [EN.render("welcome")]
    assert s.state == "lang"


def test_unknown_place_asks_again() -> None:
    s, replies = run(["hi", "2", "yes", "Atlantis"])

    assert replies[3] == [EN.render("location_not_understood")]
    assert s.state == "location"


def test_unknown_crop_asks_again() -> None:
    s, replies = run(["hi", "2", "yes", "Dindigul", "dragon fruit"])

    assert replies[4][0].startswith("Sorry, I didn't catch the crop")
    assert s.state == "crops"


# ---------- advice ----------


def test_confirms_before_advising_then_advises() -> None:
    ports = FakePorts()

    s, replies = run(["20 quintal thakkali", "1"], session=onboarded(), ports=ports)

    assert replies[0] == [
        EN.render("confirm_query", crop="Tomato", quantity="20 quintals", place="Dindigul")
    ]
    assert ports.advise_calls == [
        {"commodity": "tomato", "quantity": 20, "unit": "quintal", "lat": 10.3624, "lon": 77.9695}
    ]
    assert replies[1][0] == advice_message(ports.advice, "en", place="Dindigul")
    assert s.state == "idle"
    assert s.pending == {}


def test_disclaimer_once_per_day() -> None:
    s, first = run(["20 quintal thakkali", "1"], session=onboarded())
    _, second = run(["20 quintal thakkali", "1"], session=s)

    assert first[1][-1] == EN.render("disclaimer")
    assert EN.render("disclaimer") not in second[1]


def test_asks_for_missing_quantity_then_confirms() -> None:
    s, replies = run(["thakkali", "20 quintal"], session=onboarded())

    assert replies[0] == [EN.render("ask_quantity", crop="Tomato")]
    assert replies[1][0].startswith("Confirm: Tomato, 20 quintals")
    assert s.state == "confirm_query"


def test_single_crop_farmer_does_not_need_to_name_it() -> None:
    _, replies = run(["20 quintal"], session=onboarded(crops=["turmeric"]))

    assert replies[0][0].startswith("Confirm: Turmeric, 20 quintals")


def test_asks_which_crop_when_it_is_unclear() -> None:
    _, replies = run(["20 quintal"], session=onboarded())

    assert replies[0][0].startswith("Which crop do you want to sell?")


def test_bare_number_means_quintals_and_is_confirmed() -> None:
    _, replies = run(["thakkali 20"], session=onboarded())

    assert replies[0][0].startswith("Confirm: Tomato, 20 quintals")


def test_other_units_are_converted_before_confirming() -> None:
    _, replies = run(["2000 kg thakkali"], session=onboarded())

    assert replies[0][0].startswith("Confirm: Tomato, 20 quintals")


def test_unknown_pack_weight_asks_for_a_standard_unit() -> None:
    s, replies = run(["10 crate manjal"], session=onboarded())

    assert replies[0] == [EN.render("unit_not_understood")]
    assert "quantity" not in s.pending


def test_place_in_the_question_overrides_the_farm_location() -> None:
    ports = FakePorts()

    _, replies = run(["20 quintal thakkali Palani pakkam", "1"], session=onboarded(), ports=ports)

    assert "from Palani" in replies[0][0]
    assert (ports.advise_calls[0]["lat"], ports.advise_calls[0]["lon"]) == (10.45, 77.5161)


def test_never_advises_without_a_location() -> None:
    ports = FakePorts()
    nowhere = onboarded()
    nowhere.lat = nowhere.lon = None
    nowhere.place = None

    s, replies = run(["20 quintal thakkali", "1"], session=nowhere, ports=ports)

    assert replies[1] == [EN.render("ask_location")]
    assert ports.advise_calls == []
    assert s.state == "location"


def test_saying_change_at_confirmation_starts_over() -> None:
    ports = FakePorts()

    s, replies = run(["20 quintal thakkali", "2"], session=onboarded(), ports=ports)

    assert replies[1] == [EN.render("change_what")]
    assert ports.advise_calls == []
    assert (s.state, s.pending) == ("idle", {})


def test_a_new_question_at_confirmation_replaces_the_old_one() -> None:
    s, replies = run(["20 quintal thakkali", "15 quintal manjal"], session=onboarded())

    assert replies[1][0].startswith("Confirm: Turmeric, 15 quintals")
    assert s.state == "confirm_query"


def test_advice_in_tamil() -> None:
    ports = FakePorts()

    _, replies = run(["20 குவிண்டால் தக்காளி", "ஆம்"], session=onboarded("ta"), ports=ports)

    assert replies[0][0].startswith("உறுதி செய்யவும்: தக்காளி, 20 குவிண்டால்")
    assert replies[1][0] == advice_message(ports.advice, "ta", place="Dindigul")


# ---------- other intents ----------


def test_price_at_one_mandi() -> None:
    quote = PriceQuote("oddanchatram", date(2026, 11, 18), 2300.0, 2450.0, 2600.0)
    ports = FakePorts(prices={("tomato", "oddanchatram"): quote})

    _, replies = run(["price tomato Oddanchatram"], session=onboarded(), ports=ports)

    assert replies[0] == [
        EN.render(
            "price", crop="Tomato", market="Oddanchatram", modal="2,450", low="2,300",
            high="2,600", date="18 Nov",
        )
    ]  # fmt: skip


def test_price_without_data_says_so() -> None:
    _, replies = run(["price tomato Oddanchatram"], session=onboarded())

    assert replies[0] == [EN.render("price_no_data", crop="Tomato", market="Oddanchatram")]


def test_price_without_a_mandi_asks_which() -> None:
    _, replies = run(["thakkali rate enna"], session=onboarded())

    assert replies[0] == [EN.render("price_which_market", crop="Tomato")]


def test_commands_in_idle() -> None:
    s, replies = run(["help"], session=onboarded())
    assert replies[0] == [EN.render("help")]

    s, replies = run(["change crops"], session=onboarded())
    assert s.state == "crops"

    s, replies = run(["change location"], session=onboarded())
    assert s.state == "location"

    s, replies = run(["alert"], session=onboarded())
    assert replies[0] == [EN.render("alerts_coming_soon")]


def test_switching_language_keeps_the_profile() -> None:
    s, replies = run(["language", "1"], session=onboarded("en"))

    assert replies[0] == [EN.render("language_prompt")]
    assert (s.state, s.language, s.crops) == ("idle", "ta", ["tomato", "turmeric"])
    assert replies[1] == [TA.render("help")]


def test_changing_location_after_onboarding_returns_to_idle() -> None:
    s, _ = run(["change location", "Palani"], session=onboarded())

    assert (s.state, s.place, s.crops) == ("idle", "Palani", ["tomato", "turmeric"])


def test_voice_notes_are_not_supported_yet() -> None:
    audio = InboundMessage(
        channel="test", message_id="m", sender="+919876543210", kind="audio",
        media_url="https://x/y", media_type="audio/ogg",
    )  # fmt: skip

    s, replies = run([audio], session=onboarded())

    assert replies[0] == [EN.render("audio_coming_soon")]
    assert s.state == "idle"


def test_gibberish_gets_the_short_help() -> None:
    _, replies = run(["asdf qwerty"], session=onboarded())

    assert replies[0] == [EN.render("unknown")]
