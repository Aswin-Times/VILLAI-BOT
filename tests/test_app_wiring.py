"""Which intent parser and channel the app picks from settings."""

from __future__ import annotations

from app.channels.logging_channel import LoggingChannel
from app.channels.twilio_whatsapp import TwilioWhatsAppChannel
from app.config import Settings
from app.conversation.llm_parser import AnthropicIntentParser
from app.conversation.rules_parser import RulesParser
from app.main import build_channel, build_parser

RULES = RulesParser.from_reference()


def s(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


def test_rules_parser_by_default() -> None:
    assert build_parser(s(), RULES) is RULES


def test_claude_parser_when_configured() -> None:
    parser = build_parser(s(intent_provider="anthropic", anthropic_api_key="sk-test"), RULES)

    assert isinstance(parser, AnthropicIntentParser)


def test_falls_back_to_rules_without_an_api_key() -> None:
    assert build_parser(s(intent_provider="anthropic"), RULES) is RULES


def test_twilio_channel_only_with_credentials() -> None:
    assert isinstance(build_channel(s()), LoggingChannel)
    channel = build_channel(s(twilio_account_sid="AC1", twilio_auth_token="tok"))
    assert isinstance(channel, TwilioWhatsAppChannel)
