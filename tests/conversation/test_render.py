"""Reply templates: formatting, language parity and the advice message."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pytest

from app.conversation.render import (
    Renderer,
    advice_message,
    fmt_date,
    fmt_quantity,
    inr,
    template_keys,
)
from app.schemas.advice import AdviceResponse, GlutOut, MarketOption

LANGS = ("en", "ta")
SAMPLE: dict[str, Any] = {
    "crop": "Tomato",
    "crops": "Tomato, Banana",
    "crop_list": "Tomato, Small onion, Turmeric, Banana",
    "quantity": "20 quintals",
    "place": "Dindigul",
    "market": "Oddanchatram",
    "modal": "2,450",
    "low": "2,300",
    "high": "2,600",
    "date": "18 Nov",
}


def test_indian_digit_grouping() -> None:
    assert inr(999) == "999"
    assert inr(46600) == "46,600"
    assert inr(198975) == "1,98,975"
    assert inr(1234567) == "12,34,567"
    assert inr(-1200) == "-1,200"
    assert inr(2449.6) == "2,450"


def test_dates_in_both_languages() -> None:
    assert fmt_date(date(2026, 11, 18), "en") == "18 Nov"
    assert fmt_date(date(2026, 11, 18), "ta") == "18 நவம்பர்"


def test_quantities_in_both_languages() -> None:
    assert fmt_quantity(20, "en") == "20 quintals"
    assert fmt_quantity(1, "en") == "1 quintal"
    assert fmt_quantity(2.5, "en") == "2.5 quintals"
    assert fmt_quantity(20, "ta") == "20 குவிண்டால்"


def test_every_message_exists_in_both_languages() -> None:
    assert template_keys("en") == template_keys("ta")


@pytest.mark.parametrize("lang", LANGS)
def test_every_template_renders_with_known_variables(lang: str) -> None:
    r = Renderer(lang)
    for key in template_keys(lang) - {"advice"}:
        assert r.render(key, **SAMPLE).strip(), key


def test_tamil_messages_are_in_tamil() -> None:
    r = Renderer("ta")
    for key in template_keys("ta") - {"advice", "welcome"}:
        assert re.search(r"[஀-௿]", r.render(key, **SAMPLE)), key


def option(code: str, name: str, net: float, km: float, **kw: Any) -> MarketOption:
    base: dict[str, Any] = {
        "market_code": code,
        "market_name": name,
        "obs_date": date(2026, 11, 18),
        "stale": False,
        "distance_km": km,
        "modal_price": 2450.0,
        "deductions_per_q": 196.0,
        "transport_per_q": 92.4,
        "net_per_q": net,
        "net_per_q_low": net - 100,
        "net_per_q_high": net + 100,
        "total_net": net * 20,
        "glut": GlutOut(
            flagged=False, arrivals_tonnes=None, baseline_tonnes=None, pct_above_normal=None,
            reason="no_arrivals_today",
        ),
    }  # fmt: skip
    base.update(kw)
    return MarketOption.model_validate(base)


def response(**kw: Any) -> AdviceResponse:
    spike = GlutOut(
        flagged=True, arrivals_tonnes=270, baseline_tonnes=187.5, pct_above_normal=44.0, reason=None
    )
    base: dict[str, Any] = {
        "recommendation_id": 1,
        "commodity_code": "tomato",
        "quantity_quintals": 20,
        "data_as_of": date(2026, 11, 18),
        "best_market_code": "oddanchatram",
        "nearest_market_code": "dindigul",
        "extra_vs_nearest": 2739.35,
        "options": [
            option("oddanchatram", "Oddanchatram", 2316.04, 34.6, glut=spike),
            option("dindigul", "Dindigul", 2179.0, 1.7, modal_price=2450.0),
            option("palani", "Palani", 2158.85, 64.2),
        ],
        "regional_glut": False,
        "excluded": {},
        "warnings": [],
    }
    base.update(kw)
    return AdviceResponse.model_validate(base)


def test_english_advice_message() -> None:
    text = advice_message(response(), "en", place="Dindigul")

    assert text == (
        "Tomato · 20 quintals · prices as of 18 Nov\n"
        "1. Oddanchatram — ₹2,450/q · 35 km → you keep ≈ ₹2,320/q (≈ ₹46,300)\n"
        "2. Dindigul — ₹2,450/q · 2 km → you keep ≈ ₹2,180/q (≈ ₹43,600)\n"
        "3. Palani — ₹2,450/q · 64 km → you keep ≈ ₹2,160/q (≈ ₹43,200)\n"
        "⚠ Oddanchatram: arrivals 44% above normal — prices may soften.\n"
        "Oddanchatram gives ≈ ₹2,700 more than the nearest mandi (Dindigul)."
    )


def test_tamil_advice_uses_tamil_names_and_the_same_numbers() -> None:
    text = advice_message(response(), "ta", place="திண்டுக்கல்")

    assert "தக்காளி" in text
    assert "ஒட்டன்சத்திரம்" in text
    assert "18 நவம்பர்" in text
    assert "₹2,320" in text and "₹46,300" in text


@pytest.mark.parametrize("lang", LANGS)
def test_advice_fits_in_eight_lines_even_with_every_warning(lang: str) -> None:
    resp = response(
        regional_glut=True,
        warnings=["stale_data", "commodity_mapping_unverified"],
        best_market_code=None,
    )

    text = advice_message(resp, lang, place="Dindigul")

    assert len(text.splitlines()) <= 8
    assert len(text) <= 1600


@pytest.mark.parametrize("lang", LANGS)
def test_stale_options_show_their_own_date(lang: str) -> None:
    old = option("palani", "Palani", 2000.0, 64.2, stale=True, obs_date=date(2026, 11, 12))
    resp = response(options=[old], best_market_code=None, extra_vs_nearest=None,
                    warnings=["stale_data"])  # fmt: skip

    text = advice_message(resp, lang, place="Dindigul")

    assert fmt_date(date(2026, 11, 12), lang) in text


@pytest.mark.parametrize("lang", LANGS)
def test_no_data_reply_does_not_invent_numbers(lang: str) -> None:
    resp = response(
        options=[], best_market_code=None, nearest_market_code=None, extra_vs_nearest=None,
        data_as_of=None, warnings=["no_recent_data"],
    )  # fmt: skip

    text = advice_message(resp, lang, place="Dindigul")

    assert "₹" not in text
