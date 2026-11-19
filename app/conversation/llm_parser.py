"""Intent parsing with Claude Haiku (plan §5), behind the IntentParser interface.

The model only fills structured fields, validated by a Pydantic schema whose
crop and market fields accept nothing outside the seed. It never writes
replies or numbers for the farmer. Any failure (refusal, timeout, API error)
raises, and the conversation service falls back to the rules parser.

Only the message text is sent: never the phone number or profile.
"""

from __future__ import annotations

from functools import cache
from typing import Literal

import anthropic
from pydantic import BaseModel

from app.conversation.intents import Intent, ParsedIntent, Unit
from app.data.reference import load_commodities, load_markets

MODEL = "claude-haiku-5-5"
MAX_TOKENS = 2048  # thinking counts against this; the JSON itself is tiny

# Kept in step with the seed files by tests/conversation/test_llm_parser.py.
CropCode = Literal["tomato", "small_onion", "turmeric", "banana"]
MarketCode = Literal[
    "oddanchatram", "dindigul", "palani", "coimbatore", "mettupalayam", "pollachi",
    "udumalpet", "tiruppur", "erode", "namagiripettai", "salem", "perambalur",
    "madurai", "krishnagiri", "hosur",
]  # fmt: skip


class IntentParserError(RuntimeError):
    pass


class LLMIntent(BaseModel):
    """What the model must return. Every field is required; unknowns are null."""

    intent: Intent
    commodity: CropCode | None
    quantity: float | None
    unit: Unit | None
    location_text: str | None
    market: MarketCode | None


@cache
def system_prompt() -> str:
    crops = "\n".join(f"  {c.code}: {', '.join(c.synonyms)}" for c in load_commodities())
    markets = "\n".join(f"  {m.code}: {', '.join(m.aliases)}" for m in load_markets())
    return f"""You turn a Tamil Nadu farmer's WhatsApp message into structured fields for a \
mandi-price bot. Messages may be in English, Tamil script, transliterated Tamil, or a mix.

Fields:
- intent:
  advice = wants to know where to sell or which mandi pays best, or states a crop and an amount
  price = asks the price of a crop at one named mandi
  help, alert (daily price alerts), stop, change_crops, change_location, language, greeting
  yes / no = a reply such as 1/2, yes/no, ஆம்/இல்லை, sari/illa
  unknown = anything else
- commodity: the code of the crop the message names, from this list only:
{crops}
  A bare "onion", "vengayam" or "வெங்காயம்" is ambiguous (small or big onion): use null.
- quantity and unit: only if the message states an amount. unit is one of quintal, kg, tonne,
  bag (mootai, மூட்டை) or crate (petti, பெட்டி, box). Write number words as digits
  (irubathu or இருபது = 20). A number with no unit: give the quantity and a null unit.
- location_text: a place the farmer says they are at, near or coming from ("Dindigul pakkam",
  "near Palani", "Erode side"), copied as written. Otherwise null.
- market: only for price questions, the code of the mandi asked about:
{markets}

Never guess. If a field is not clearly in the message, use null. Do not answer the farmer and \
do not add any numbers that are not in the message: only fill the fields."""


class AnthropicIntentParser:
    name = "anthropic"

    def __init__(self, client: anthropic.Anthropic, model: str = MODEL) -> None:
        self._client = client
        self._model = model

    def parse(self, text: str) -> ParsedIntent:
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system_prompt(),
            messages=[{"role": "user", "content": text}],
            output_format=LLMIntent,
            output_config={"effort": "low"},
        )
        if response.stop_reason == "refusal":
            raise IntentParserError("model returned a refusal")
        out = response.parsed_output
        if out is None:
            raise IntentParserError(f"no structured output (stop_reason={response.stop_reason})")
        quantity = out.quantity if out.quantity is not None and out.quantity > 0 else None
        return ParsedIntent(
            intent=out.intent,
            commodity=out.commodity,
            quantity=quantity,
            unit=out.unit if quantity is not None else None,
            location_text=(out.location_text or "").strip() or None,
            market=out.market,
        )
