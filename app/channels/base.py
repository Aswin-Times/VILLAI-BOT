"""Channel-neutral message types. Twilio today; Meta Cloud API or Telegram later."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class ChannelError(RuntimeError):
    """Sending failed."""


class InboundMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    channel: str
    message_id: str
    sender: str  # E.164
    kind: Literal["text", "audio", "location", "other"]
    text: str | None = None
    lat: float | None = None
    lon: float | None = None
    media_url: str | None = None
    media_type: str | None = None


class Channel(Protocol):
    name: str

    def send_text(self, to: str, body: str) -> None: ...
