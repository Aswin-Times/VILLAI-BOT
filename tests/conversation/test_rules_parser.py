"""Rules-based intent parser: the deterministic fallback, measured on the golden set."""

from __future__ import annotations

import pytest

from app.conversation.intents import ParsedIntent
from app.conversation.rules_parser import RulesParser
from tests.conversation.golden import score

PARSER = RulesParser.from_reference()


def test_golden_set_accuracy_is_at_least_90_percent() -> None:
    accuracy, misses = score(PARSER)

    report = "\n".join(f"  {m.text!r}: expected {m.expected}, got {m.got}" for m in misses)
    print(f"rules parser golden accuracy: {accuracy:.1%}\n{report}")
    assert accuracy >= 0.90, f"accuracy {accuracy:.1%}; misses:\n{report}"


def test_number_with_thousands_separator() -> None:
    p = PARSER.parse("1,500 kg tomato")

    assert (p.quantity, p.unit) == (1500, "kg")


def test_unit_attached_to_number() -> None:
    assert PARSER.parse("thakkali 20kg").unit == "kg"


def test_bare_number_has_no_unit() -> None:
    p = PARSER.parse("thakkali 10")

    assert (p.quantity, p.unit) == (10, None)


def test_tamil_suffix_on_crop_and_place() -> None:
    p = PARSER.parse("திண்டுக்கல்லில் இருந்து தக்காளியை விற்கணும்")

    assert p.commodity == "tomato"
    assert p.intent == "advice"


@pytest.mark.parametrize("text", ["", "   ", "🙏"])
def test_empty_or_emoji_only_is_unknown(text: str) -> None:
    assert PARSER.parse(text) == ParsedIntent(intent="unknown")


def test_help_inside_a_sentence_is_not_the_help_command() -> None:
    assert PARSER.parse("help me sell 20 quintal tomato").intent == "advice"


def test_crops_in_lists_every_crop_once_in_order() -> None:
    assert PARSER.crops_in("thakkali, manjal and tomato") == ["tomato", "turmeric"]
    assert PARSER.crops_in("வாழைப்பழம், சின்ன வெங்காயம்") == ["banana", "small_onion"]
    assert PARSER.crops_in("rice") == []
