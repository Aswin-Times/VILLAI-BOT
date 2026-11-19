"""Phone-number handling.

- `normalise_phone` turns Twilio's `whatsapp:+91...` into E.164.
- `hash_phone` keys pre-consent conversation state, so nothing identifying is
  stored before the farmer says YES (CLAUDE.md: no farmer data before consent).
- `mask_phone` is the only form a number may take in logs.
"""

from __future__ import annotations

import hashlib
import hmac
import re

_NON_DIGIT = re.compile(r"[^\d+]")


def normalise_phone(raw: str) -> str:
    s = raw.strip()
    if s.lower().startswith("whatsapp:"):
        s = s[len("whatsapp:") :]
    s = _NON_DIGIT.sub("", s)
    if not re.fullmatch(r"\+\d{7,15}", s):
        raise ValueError("not an E.164 phone number")
    return s


def hash_phone(phone_e164: str, secret: str) -> str:
    return hmac.new(secret.encode(), phone_e164.encode(), hashlib.sha256).hexdigest()


def mask_phone(phone_e164: str) -> str:
    if len(phone_e164) < 9:
        return "+" + "*" * 6
    return phone_e164[:3] + "*" * (len(phone_e164) - 7) + phone_e164[-4:]
