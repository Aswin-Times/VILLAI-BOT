"""A channel that only logs, for local runs without Twilio credentials."""

from __future__ import annotations

import logging

from app.privacy import mask_phone

log = logging.getLogger("vilai.channel")


class LoggingChannel:
    name = "log"

    def send_text(self, to: str, body: str) -> None:
        log.info("[not sent: no Twilio credentials] to %s:\n%s", mask_phone(to), body)
