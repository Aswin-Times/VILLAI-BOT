"""Twilio WhatsApp channel: parse inbound webhooks, verify signatures, send replies."""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from app.channels.base import ChannelError
from app.channels.twilio_whatsapp import (
    TwilioWhatsAppChannel,
    parse_inbound,
    twilio_signature,
    verify_signature,
)

# Reference values computed with Twilio's official SDK (twilio 9.13.0 RequestValidator).
DOC_URL = "https://mycompany.com/myapp.php?foo=1&bar=2"
DOC_PARAMS = {
    "CallSid": "CA1234567890ABCDE",
    "Caller": "+12349013030",
    "Digits": "1234",
    "From": "+12349013030",
    "To": "+18005551212",
}
TAMIL_URL = "https://vilai.example/webhooks/twilio/whatsapp"
TAMIL_PARAMS = {
    "From": "whatsapp:+919876543210",
    "Body": "சின்ன வெங்காயம் 20 குவிண்டால்",
    "MessageSid": "SM123",
    "NumMedia": "0",
}


def test_signature_matches_twilio_documented_example() -> None:
    assert twilio_signature("12345", DOC_URL, DOC_PARAMS) == "0/KCTR6DLpKmkAf8muzZqo1nDgQ="


def test_signature_handles_tamil_text() -> None:
    assert twilio_signature("12345", TAMIL_URL, TAMIL_PARAMS) == "7HmIU2zYSjEDjenHNZkS+bIL3m0="


def test_verify_accepts_good_and_rejects_tampered_requests() -> None:
    good = twilio_signature("12345", TAMIL_URL, TAMIL_PARAMS)

    assert verify_signature("12345", TAMIL_URL, TAMIL_PARAMS, good)
    assert not verify_signature("12345", TAMIL_URL, {**TAMIL_PARAMS, "Body": "50 q"}, good)
    assert not verify_signature("wrong-token", TAMIL_URL, TAMIL_PARAMS, good)
    assert not verify_signature("12345", TAMIL_URL, TAMIL_PARAMS, None)


def test_parses_text_message() -> None:
    msg = parse_inbound(TAMIL_PARAMS)

    assert msg.message_id == "SM123"
    assert msg.sender == "+919876543210"
    assert msg.kind == "text"
    assert msg.text == "சின்ன வெங்காயம் 20 குவிண்டால்"


def test_parses_location_pin() -> None:
    msg = parse_inbound(
        {
            "From": "whatsapp:+919876543210",
            "MessageSid": "SM2",
            "Latitude": "10.3624",
            "Longitude": "77.9695",
            "NumMedia": "0",
            "Body": "",
        }
    )

    assert msg.kind == "location"
    assert (msg.lat, msg.lon) == (10.3624, 77.9695)


def test_parses_voice_note() -> None:
    msg = parse_inbound(
        {
            "From": "whatsapp:+919876543210",
            "MessageSid": "SM3",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/ME1",
            "MediaContentType0": "audio/ogg",
            "Body": "",
        }
    )

    assert msg.kind == "audio"
    assert msg.media_url == "https://api.twilio.com/media/ME1"
    assert msg.media_type == "audio/ogg"


def test_images_and_other_media_are_other() -> None:
    msg = parse_inbound(
        {
            "From": "whatsapp:+919876543210",
            "MessageSid": "SM4",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/ME2",
            "MediaContentType0": "image/jpeg",
            "Body": "",
        }
    )

    assert msg.kind == "other"


def test_send_posts_to_twilio_messages_api() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"sid": "SM9"})

    channel = TwilioWhatsAppChannel(
        account_sid="AC123",
        auth_token="tok",
        from_number="whatsapp:+14155238886",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    channel.send_text("+919876543210", "வணக்கம்")

    (req,) = seen
    assert req.url == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    form = parse_qs(req.content.decode())
    assert form == {
        "From": ["whatsapp:+14155238886"],
        "To": ["whatsapp:+919876543210"],
        "Body": ["வணக்கம்"],
    }
    assert req.headers["authorization"].startswith("Basic ")


def test_send_failure_raises_without_leaking_the_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Authenticate"})

    channel = TwilioWhatsAppChannel(
        account_sid="AC123",
        auth_token="super-secret-token",
        from_number="whatsapp:+14155238886",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ChannelError) as exc:
        channel.send_text("+919876543210", "hi")

    assert "401" in str(exc.value)
    assert "super-secret-token" not in str(exc.value)


def test_refuses_messages_over_twilio_length_limit() -> None:
    channel = TwilioWhatsAppChannel("AC1", "t", "whatsapp:+1", client=httpx.Client())

    with pytest.raises(ValueError):
        channel.send_text("+919876543210", "x" * 1601)
