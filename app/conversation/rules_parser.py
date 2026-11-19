"""Deterministic intent parser for English, transliterated Tamil and Tamil script.

The fallback when the LLM parser is off or fails, and the parser CI measures
on the golden set. Vocabulary for crops and places comes from the seed files.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.conversation.intents import Intent, ParsedIntent, Unit
from app.data.reference import load_commodities, load_markets

_TAMIL = re.compile(r"[஀-௿]")

# Whole-message commands.
_EXACT: dict[str, Intent] = {
    **dict.fromkeys(["help", "menu", "உதவி", "udhavi", "help me"], "help"),
    **dict.fromkeys(["alert", "alerts", "அலர்ட்", "daily price"], "alert"),
    **dict.fromkeys(["stop", "unsubscribe", "நிறுத்து", "niruthu"], "stop"),
    **dict.fromkeys(
        ["change crops", "change crop", "my crops", "பயிர் மாற்று", "payir maathu"], "change_crops"
    ),
    **dict.fromkeys(
        ["change location", "new location", "இடம் மாற்று", "idam maathu"], "change_location"
    ),
    **dict.fromkeys(["language", "change language", "மொழி", "mozhi"], "language"),
    **dict.fromkeys(
        ["hi", "hii", "hello", "hai", "hey", "vanakkam", "வணக்கம்", "good morning"], "greeting"
    ),
    **dict.fromkeys(
        ["1", "yes", "y", "ok", "okay", "ஆம்", "ஆமா", "aama", "aamaa", "sari", "சரி", "correct"],
        "yes",
    ),
    **dict.fromkeys(["2", "no", "n", "இல்லை", "illa", "illai", "venam", "வேண்டாம்"], "no"),
}

_UNITS: dict[str, Unit] = {
    **dict.fromkeys(["quintal", "quintals", "qtl", "qtls", "q", "kuvintal"], "quintal"),
    **dict.fromkeys(["kg", "kgs", "kilo", "kilos", "kilogram", "kilograms"], "kg"),
    **dict.fromkeys(["ton", "tons", "tonne", "tonnes", "t"], "tonne"),
    **dict.fromkeys(["bag", "bags", "mootai", "moottai", "mutai"], "bag"),
    **dict.fromkeys(["crate", "crates", "box", "boxes", "petti"], "crate"),
}
_TAMIL_UNITS: dict[str, Unit] = {
    "குவிண்டால்": "quintal",
    "குவின்டால்": "quintal",
    "கிலோ": "kg",
    "டன்": "tonne",
    "மூட்டை": "bag",
    "பெட்டி": "crate",
}
_NUMBER_WORDS: dict[str, float] = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "hundred": 100,
    # Transliterated Tamil
    "onnu": 1, "ondru": 1, "rendu": 2, "moonu": 3, "naalu": 4, "anju": 5, "aaru": 6,
    "ezhu": 7, "ettu": 8, "onbathu": 9, "pathu": 10, "irubathu": 20, "muppathu": 30,
    "naarpathu": 40, "aimbathu": 50, "ambathu": 50, "nooru": 100,
    # Tamil script
    "ஒன்று": 1, "இரண்டு": 2, "ரெண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5,
    "அஞ்சு": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10,
    "இருபது": 20, "முப்பது": 30, "நாற்பது": 40, "ஐம்பது": 50, "நூறு": 100,
}  # fmt: skip

_PRICE_WORDS = {"price", "prices", "rate", "rates", "vilai", "vela"}
_PRICE_WORDS_TA = ("விலை", "ரேட்")
_ADVICE_WORDS = {
    "sell", "selling", "where", "which", "best", "enga", "engae", "enge",
    "vikka", "vikkalam", "vikkanum", "vikkradhu", "pogalam", "virkka",
}  # fmt: skip
_ADVICE_WORDS_TA = ("விற்க", "விக்க", "எங்க", "எங்கே", "சிறந்த")

# Place markers: "<place> pakkam", "near <place>", "<place> la irundhu", ...
_AFTER_PLACE = ("pakkam", "side", "area", "arugil", "பக்கம்", "அருகில்", "la irundhu", "ல இருந்து")
_BEFORE_PLACE = ("near", "from")
_NOT_PLACES = {"sir", "my", "the", "of", "i", "and", "market", "mandi"}


def _clean(text: str) -> str:
    t = text.casefold()
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)  # 1,500 -> 1500
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)  # full stops, not decimal points
    # Punctuation, including the curly quotes phone keyboards insert.
    t = re.sub(r"[?!,;:()\"'“”‘’\-/]", " ", t)  # noqa: RUF001 - curly quotes are intended
    return " ".join(t.split())


def _is_tamil(s: str) -> bool:
    return bool(_TAMIL.search(s))


@dataclass(frozen=True)
class _Term:
    phrase: str
    value: str


def _find(text: str, terms: Iterable[_Term]) -> list[tuple[int, _Term, str]]:
    """Occurrences as (position, term, matched text). Tamil terms match as prefixes
    of words (Tamil adds suffixes); Latin terms allow a short plural/case suffix."""
    found: list[tuple[int, _Term, str]] = []
    for term in terms:
        if _is_tamil(term.phrase):
            pattern = re.escape(term.phrase) + r"[஀-௿]*"
        else:
            pattern = r"(?<![a-z])" + re.escape(term.phrase) + r"[a-z]{0,3}(?![a-z])"
        for m in re.finditer(pattern, text):
            found.append((m.start(), term, m.group(0)))
    return sorted(found, key=lambda f: (f[0], -len(f[1].phrase)))


class RulesParser:
    name = "rules"

    def __init__(self, crops: Iterable[_Term], places: Iterable[_Term]) -> None:
        # Longest phrase first, so "chinna vengayam" beats any shorter overlap.
        self._crops = sorted(crops, key=lambda term: -len(term.phrase))
        self._places = sorted(places, key=lambda term: -len(term.phrase))

    @classmethod
    def from_reference(cls) -> RulesParser:
        crops = [_Term(s, c.code) for c in load_commodities() for s in c.synonyms]
        places = [_Term(a, m.code) for m in load_markets() for a in m.aliases]
        return cls(crops, places)

    def parse(self, text: str) -> ParsedIntent:
        t = _clean(text)
        if not t or not re.search(r"[a-z0-9஀-௿]", t):
            return ParsedIntent(intent="unknown")
        if t in _EXACT:
            return ParsedIntent(intent=_EXACT[t])

        crop_hits = _find(t, self._crops)
        commodity = crop_hits[0][1].value if crop_hits else None
        quantity, unit = self._quantity(t.split())
        location_text, location_code = self._location(t)
        market = self._market(t, exclude=location_code)

        tokens = set(t.split())
        has_price = bool(tokens & _PRICE_WORDS) or any(w in t for w in _PRICE_WORDS_TA)
        has_advice = bool(tokens & _ADVICE_WORDS) or any(w in t for w in _ADVICE_WORDS_TA)

        if has_price and not has_advice and quantity is None:
            return ParsedIntent(intent="price", commodity=commodity, market=market)
        if commodity or quantity or has_advice:
            place = location_text or self._first_place_text(t)
            return ParsedIntent(
                intent="advice",
                commodity=commodity,
                quantity=quantity,
                unit=unit,
                location_text=place,
            )
        return ParsedIntent(intent="unknown")

    def crops_in(self, text: str) -> list[str]:
        """Every pilot crop named in the text, in order, without repeats."""
        codes: list[str] = []
        for _pos, term, _matched in _find(_clean(text), self._crops):
            if term.value not in codes:
                codes.append(term.value)
        return codes

    def _quantity(self, tokens: list[str]) -> tuple[float | None, Unit | None]:
        for i, tok in enumerate(tokens):
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            m = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]*)", tok)
            if m:
                value = float(m.group(1))
                if value <= 0:
                    continue
                attached = m.group(2)
                if attached:
                    unit = _unit(attached)
                    if unit is None:
                        continue  # e.g. "18th"
                    return value, unit
                return value, _unit(nxt)
            if tok in _NUMBER_WORDS and _unit(nxt):
                return _NUMBER_WORDS[tok], _unit(nxt)
        return None, None

    def _location(self, t: str) -> tuple[str | None, str | None]:
        tokens = t.split()
        for marker in _AFTER_PLACE:
            m = re.search(r"(\S+) " + re.escape(marker) + r"(?!\S)", t)
            if m and m.group(1) not in _NOT_PLACES and not _is_number(m.group(1)):
                return m.group(1), self._place_code(m.group(1))
        for i, tok in enumerate(tokens[:-1]):
            if tok in _BEFORE_PLACE and tokens[i + 1] not in _NOT_PLACES:
                return tokens[i + 1], self._place_code(tokens[i + 1])
        return None, None

    def _place_code(self, word: str) -> str | None:
        hits = _find(word, self._places)
        return hits[0][1].value if hits else None

    def _market(self, t: str, exclude: str | None) -> str | None:
        for _pos, term, _text in _find(t, self._places):
            if term.value != exclude:
                return term.value
        return None

    def _first_place_text(self, t: str) -> str | None:
        hits = _find(t, self._places)
        return hits[0][2] if hits else None


def _unit(word: str) -> Unit | None:
    if word in _UNITS:
        return _UNITS[word]
    for tamil, unit in _TAMIL_UNITS.items():
        if word.startswith(tamil):
            return unit
    return None


def _is_number(word: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", word)) or word in _NUMBER_WORDS
