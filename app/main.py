"""FastAPI application factory."""

from __future__ import annotations

import logging

import anthropic
from fastapi import FastAPI

from app.api import advice, reference, webhooks_twilio
from app.channels.base import Channel
from app.channels.logging_channel import LoggingChannel
from app.channels.twilio_whatsapp import TwilioWhatsAppChannel
from app.clock import today_ist
from app.config import Settings
from app.conversation.geocode import ReferenceGeocoder
from app.conversation.intents import IntentParser
from app.conversation.llm_parser import AnthropicIntentParser
from app.conversation.rules_parser import RulesParser
from app.db import make_engine, make_sessionmaker


def build_channel(settings: Settings) -> Channel:
    if settings.twilio_account_sid and settings.twilio_auth_token:
        return TwilioWhatsAppChannel(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token.get_secret_value(),
            from_number=settings.twilio_whatsapp_from,
        )
    return LoggingChannel()


log = logging.getLogger("vilai")


def build_parser(settings: Settings, rules: RulesParser) -> IntentParser:
    if settings.intent_provider == "anthropic":
        if settings.anthropic_api_key is None:
            log.warning("INTENT_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set; using rules")
            return rules
        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=8.0,  # the farmer is waiting; rules answer if Claude is slow
            max_retries=1,
        )
        return AnthropicIntentParser(client)
    return rules


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Vilai", version="0.1.0")
    app.state.settings = settings
    app.state.sessionmaker = make_sessionmaker(make_engine(settings.database_url))
    app.state.channel = build_channel(settings)
    app.state.rules = RulesParser.from_reference()
    app.state.parser = build_parser(settings, app.state.rules)
    app.state.geocoder = ReferenceGeocoder.from_reference()
    app.state.today = today_ist

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(advice.router)
    app.include_router(reference.router)
    app.include_router(webhooks_twilio.router)
    return app


app = create_app()
