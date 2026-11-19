"""POST /webhooks/twilio/whatsapp: verify, acknowledge fast, process in the background.

Twilio waits only a few seconds for a response, and later phases add speech
and TTS, so the reply goes out through the REST API after this returns.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.channels.base import InboundMessage
from app.channels.twilio_whatsapp import parse_inbound, verify_signature
from app.config import Settings
from app.conversation.service import ChatDeps, process_inbound

router = APIRouter(tags=["webhooks"])
log = logging.getLogger("vilai.webhook")
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@router.post("/webhooks/twilio/whatsapp")
async def twilio_whatsapp(request: Request, background: BackgroundTasks) -> Response:
    state = request.app.state
    settings: Settings = state.settings
    form = await request.form()
    params = {k: v for k, v in form.items() if isinstance(v, str)}

    token = settings.twilio_auth_token.get_secret_value() if settings.twilio_auth_token else None
    if token is None or not verify_signature(
        token, _public_url(request, settings), params, request.headers.get("X-Twilio-Signature")
    ):
        return Response(status_code=403)
    if settings.phone_hash_secret is None:
        log.error("PHONE_HASH_SECRET is not set; refusing to process messages")
        return Response(status_code=503)
    try:
        msg = parse_inbound(params)
    except (KeyError, ValueError):
        return Response(status_code=400)

    background.add_task(_process, state, msg)
    return Response(content=EMPTY_TWIML, media_type="application/xml")


def _public_url(request: Request, settings: Settings) -> str:
    """The URL Twilio signed: the public URL, not the one behind ngrok or a proxy."""
    if not settings.public_base_url:
        return str(request.url)
    query = f"?{request.url.query}" if request.url.query else ""
    return settings.public_base_url.rstrip("/") + request.url.path + query


def _process(state: Any, msg: InboundMessage) -> None:
    settings: Settings = state.settings
    assert settings.phone_hash_secret is not None  # checked before scheduling
    deps = ChatDeps(
        parser=state.parser,
        rules=state.rules,
        geocoder=state.geocoder,
        phone_hash_secret=settings.phone_hash_secret.get_secret_value(),
        today=state.today(),
    )
    with state.sessionmaker() as db:
        process_inbound(db, msg, state.channel, deps)
