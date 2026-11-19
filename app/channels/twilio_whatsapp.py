"""Twilio WhatsApp: inbound webhook parsing, signature checks, outbound messages."""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping

import httpx

from app.channels.base import ChannelError, InboundMessage
from app.privacy import normalise_phone

API_BASE = "https://api.twilio.com/2010-04-01"
MAX_BODY_CHARS = 1600  # Twilio's limit for a WhatsApp message body


def twilio_signature(auth_token: str, url: str, params: Mapping[str, str]) -> str:
    """X-Twilio-Signature: base64(HMAC-SHA1(token, url + sorted key/value pairs))."""
    payload = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def verify_signature(
    auth_token: str, url: str, params: Mapping[str, str], signature: str | None
) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(twilio_signature(auth_token, url, params), signature)


def parse_inbound(form: Mapping[str, str]) -> InboundMessage:
    message_id, sender = form["MessageSid"], normalise_phone(form["From"])
    if form.get("Latitude") and form.get("Longitude"):
        return InboundMessage(
            channel="twilio_whatsapp",
            message_id=message_id,
            sender=sender,
            kind="location",
            lat=float(form["Latitude"]),
            lon=float(form["Longitude"]),
        )
    if int(form.get("NumMedia") or 0) > 0:
        media_type = form.get("MediaContentType0", "")
        return InboundMessage(
            channel="twilio_whatsapp",
            message_id=message_id,
            sender=sender,
            kind="audio" if media_type.startswith("audio/") else "other",
            media_url=form.get("MediaUrl0"),
            media_type=media_type,
        )
    body = (form.get("Body") or "").strip()
    return InboundMessage(
        channel="twilio_whatsapp",
        message_id=message_id,
        sender=sender,
        kind="text" if body else "other",
        text=body or None,
    )


class TwilioWhatsAppChannel:
    name = "twilio_whatsapp"

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._sid = account_sid
        self._auth = (account_sid, auth_token)
        self._from = from_number
        self._client = client or httpx.Client(timeout=20)

    def send_text(self, to: str, body: str) -> None:
        if len(body) > MAX_BODY_CHARS:
            raise ValueError(f"message is {len(body)} chars; Twilio allows {MAX_BODY_CHARS}")
        resp = self._client.post(
            f"{API_BASE}/Accounts/{self._sid}/Messages.json",
            data={"From": self._from, "To": f"whatsapp:{to}", "Body": body},
            auth=self._auth,
        )
        if resp.status_code >= 300:
            raise ChannelError(f"Twilio send failed with HTTP {resp.status_code}")
