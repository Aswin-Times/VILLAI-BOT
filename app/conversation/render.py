"""Render replies from the YAML templates.

The renderer formats numbers it is given; it never computes advice. Advice
numbers come from `AdviceResponse`, i.e. from the engine. Display rounding is
deliberate: take-home per quintal to the nearest ₹10 and totals to the
nearest ₹100, always shown with "≈".
"""

from __future__ import annotations

from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from app.data.reference import load_commodities, load_markets
from app.schemas.advice import AdviceResponse

TEMPLATE_DIR = Path(__file__).parent / "templates"
LANGUAGES = ("ta", "en")

_ENV = SandboxedEnvironment(
    undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, autoescape=False
)
_MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS_TA = [
    "ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்",
    "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்",
]  # fmt: skip


@cache
def _templates(lang: str) -> dict[str, str]:
    data: dict[str, str] = yaml.safe_load((TEMPLATE_DIR / f"{lang}.yaml").read_text("utf-8"))
    return data


def template_keys(lang: str) -> set[str]:
    return set(_templates(lang))


class Renderer:
    def __init__(self, lang: str) -> None:
        if lang not in LANGUAGES:
            raise ValueError(f"unsupported language: {lang}")
        self.lang = lang

    def render(self, key: str, **ctx: Any) -> str:
        text = _ENV.from_string(_templates(self.lang)[key]).render(**ctx)
        return "\n".join(line for line in text.splitlines() if line.strip())


def inr(amount: float) -> str:
    """Indian digit grouping: 198975 -> 1,98,975."""
    n = round(amount)
    sign, digits = ("-" if n < 0 else ""), str(abs(n))
    if len(digits) <= 3:
        return sign + digits
    head, groups = digits[:-3], [digits[-3:]]
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return sign + ",".join([head, *groups])


def round_to(amount: float, step: int) -> int:
    return int(round(amount / step) * step)


def fmt_date(d: date, lang: str) -> str:
    months = _MONTHS_TA if lang == "ta" else _MONTHS_EN
    return f"{d.day} {months[d.month - 1]}"


def fmt_quantity(quintals: float, lang: str) -> str:
    number = f"{quintals:g}"
    if lang == "ta":
        return f"{number} குவிண்டால்"
    return f"{number} quintal" if quintals == 1 else f"{number} quintals"


def crop_name(code: str, lang: str) -> str:
    c = next(c for c in load_commodities() if c.code == code)
    return c.name_ta if lang == "ta" else c.name_en


def crop_list(lang: str) -> str:
    return ", ".join(crop_name(c.code, lang) for c in load_commodities())


def market_name(code: str, lang: str, fallback: str | None = None) -> str:
    m = next((m for m in load_markets() if m.code == code), None)
    if m is None:
        return fallback or code
    return m.name_ta if lang == "ta" else m.name


def advice_message(resp: AdviceResponse, lang: str, place: str) -> str:
    r = Renderer(lang)
    crop = crop_name(resp.commodity_code, lang)
    if not resp.options or resp.data_as_of is None:
        return r.render("no_data", crop=crop, place=place)

    options = [
        {
            "market": market_name(o.market_code, lang, o.market_name),
            "modal": inr(o.modal_price),
            "km": max(1, round(o.distance_km)),
            "net": inr(round_to(o.net_per_q, 10)),
            "total": inr(round_to(o.total_net, 100)),
            "stale": o.stale,
            "date": fmt_date(o.obs_date, lang),
        }
        for o in resp.options
    ]
    flagged = next((o for o in resp.options if o.glut.flagged), None)
    glut = None
    if flagged is not None and flagged.glut.pct_above_normal is not None:
        glut = {
            "market": market_name(flagged.market_code, lang, flagged.market_name),
            "pct": round(flagged.glut.pct_above_normal),
        }
    extra = None
    if (
        resp.best_market_code
        and resp.nearest_market_code
        and resp.best_market_code != resp.nearest_market_code
        and resp.extra_vs_nearest
        and round_to(resp.extra_vs_nearest, 100) > 0
    ):
        extra = inr(round_to(resp.extra_vs_nearest, 100))

    return r.render(
        "advice",
        crop=crop,
        quantity=fmt_quantity(resp.quantity_quintals, lang),
        as_of=fmt_date(resp.data_as_of, lang),
        options=options,
        glut=glut,
        regional_glut=resp.regional_glut,
        extra=extra,
        best=market_name(resp.best_market_code, lang) if resp.best_market_code else None,
        nearest=market_name(resp.nearest_market_code, lang) if resp.nearest_market_code else None,
        stale="stale_data" in resp.warnings,
        unverified="commodity_mapping_unverified" in resp.warnings,
    )
