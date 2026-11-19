"""Claude Haiku intent parser, tested with a fake client (no API calls, no cost)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.conversation.intents import ParsedIntent
from app.conversation.llm_parser import (
    MODEL,
    AnthropicIntentParser,
    IntentParserError,
    LLMIntent,
)


class FakeMessages:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result, self.error = result, error
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def fake_client(output: LLMIntent | None, stop_reason: str = "end_turn") -> Any:
    response = SimpleNamespace(stop_reason=stop_reason, parsed_output=output)
    return SimpleNamespace(messages=FakeMessages(result=response))


def llm(**kw: Any) -> LLMIntent:
    base: dict[str, Any] = {
        "intent": "advice",
        "commodity": None,
        "quantity": None,
        "unit": None,
        "location_text": None,
        "market": None,
    }
    base.update(kw)
    return LLMIntent.model_validate(base)


def test_maps_the_model_output_to_a_parsed_intent() -> None:
    client = fake_client(
        llm(commodity="small_onion", quantity=20, unit="quintal", location_text="Dindigul")
    )

    p = AnthropicIntentParser(client).parse("20 quintal chinna vengayam, Dindigul pakkam")

    assert p == ParsedIntent(
        intent="advice",
        commodity="small_onion",
        quantity=20,
        unit="quintal",
        location_text="Dindigul",
    )


def test_request_uses_haiku_structured_output_and_low_effort() -> None:
    client = fake_client(llm())

    AnthropicIntentParser(client).parse("thakkali 10 quintal")

    (call,) = client.messages.calls
    assert call["model"] == MODEL == "claude-haiku-5-5"
    assert call["output_format"] is LLMIntent
    assert call["output_config"] == {"effort": "low"}
    assert call["messages"] == [{"role": "user", "content": "thakkali 10 quintal"}]


def test_system_prompt_carries_the_vocabulary_and_the_no_invention_rule() -> None:
    client = fake_client(llm())

    AnthropicIntentParser(client).parse("hi")

    system = client.messages.calls[0]["system"]
    assert "chinna vengayam" in system  # crop synonyms
    assert "ஒட்டன்சத்திரம்" in system  # market names in Tamil
    assert "Never guess" in system


def test_a_non_positive_quantity_is_dropped() -> None:
    client = fake_client(llm(commodity="tomato", quantity=0, unit="quintal"))

    p = AnthropicIntentParser(client).parse("thakkali")

    assert (p.quantity, p.unit) == (None, None)


def test_refusal_raises_so_the_caller_falls_back_to_rules() -> None:
    client = fake_client(None, stop_reason="refusal")

    with pytest.raises(IntentParserError, match="refusal"):
        AnthropicIntentParser(client).parse("something")


def test_missing_parsed_output_raises() -> None:
    client = fake_client(None, stop_reason="max_tokens")

    with pytest.raises(IntentParserError):
        AnthropicIntentParser(client).parse("something")


def test_api_errors_propagate_for_the_fallback() -> None:
    client = SimpleNamespace(messages=FakeMessages(error=TimeoutError("slow")))

    with pytest.raises(TimeoutError):
        AnthropicIntentParser(client).parse("something")


def test_schema_only_allows_pilot_crops_and_known_markets() -> None:
    with pytest.raises(ValueError):
        llm(commodity="rice")
    with pytest.raises(ValueError):
        llm(market="chennai")


def test_schema_codes_match_the_seed_files() -> None:
    from typing import get_args

    from app.conversation.llm_parser import CropCode, MarketCode
    from app.data.reference import load_commodities, load_markets

    assert set(get_args(CropCode)) == {c.code for c in load_commodities()}
    assert set(get_args(MarketCode)) == {m.code for m in load_markets()}


def test_service_falls_back_to_rules_when_the_llm_fails() -> None:
    from datetime import date

    from app.conversation.geocode import ReferenceGeocoder
    from app.conversation.rules_parser import RulesParser
    from app.conversation.service import ChatDeps, DbPorts

    broken = AnthropicIntentParser(
        SimpleNamespace(messages=FakeMessages(error=TimeoutError("slow")))  # type: ignore[arg-type]
    )
    deps = ChatDeps(
        parser=broken,
        rules=RulesParser.from_reference(),
        geocoder=ReferenceGeocoder.from_reference(),
        phone_hash_secret="s",
        today=date(2026, 11, 19),
    )

    p = DbPorts(None, deps, None).parse("20 quintal thakkali")  # type: ignore[arg-type]

    assert (p.intent, p.commodity, p.quantity) == ("advice", "tomato", 20)
