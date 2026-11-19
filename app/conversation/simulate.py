"""Chat with the bot in a terminal, through the real pipeline (no Twilio).

    DATABASE_URL=sqlite:///./vilai-demo.db uv run python -m app.conversation.simulate

Type messages as a farmer would. `/pin LAT LON` sends a location pin, `/quit` exits.
Uses a made-up phone number, so it creates a test farmer in whatever database
DATABASE_URL points at: use a local or demo database.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence
from datetime import date
from typing import TextIO

from app.channels.base import InboundMessage
from app.clock import today_ist
from app.config import Settings
from app.conversation.geocode import ReferenceGeocoder
from app.conversation.rules_parser import RulesParser
from app.conversation.service import ChatDeps, process_inbound
from app.db import make_engine, make_sessionmaker
from app.main import build_parser

TEST_PHONE = "+910000000001"


class PrintChannel:
    name = "print"

    def __init__(self, out: TextIO) -> None:
        self._out = out

    def send_text(self, to: str, body: str) -> None:
        print(f"\nVilai:\n{body}\n", file=self._out)


def _message(line: str, phone: str) -> InboundMessage | None:
    message_id = f"sim-{uuid.uuid4()}"
    if line.startswith("/pin"):
        try:
            _, lat, lon = line.split()
            return InboundMessage(
                channel="simulator", message_id=message_id, sender=phone,
                kind="location", lat=float(lat), lon=float(lon),
            )  # fmt: skip
        except ValueError:
            return None
    return InboundMessage(
        channel="simulator", message_id=message_id, sender=phone, kind="text", text=line
    )


def main(
    argv: Sequence[str] | None = None,
    settings: Settings | None = None,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phone", default=TEST_PHONE)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)

    settings = settings or Settings()
    secret = settings.phone_hash_secret
    rules = RulesParser.from_reference()
    deps = ChatDeps(
        parser=build_parser(settings, rules),
        rules=rules,
        geocoder=ReferenceGeocoder.from_reference(),
        phone_hash_secret=secret.get_secret_value() if secret else "local-simulator-only",
        today=args.date or today_ist(),
    )
    sessions = make_sessionmaker(make_engine(settings.database_url))
    channel = PrintChannel(stdout)
    print("Type as a farmer would. /pin LAT LON sends a location, /quit exits.", file=stdout)
    for raw in stdin:
        line = raw.strip()
        if line == "/quit":
            break
        if not line:
            continue
        print(f"You: {line}", file=stdout)
        msg = _message(line, args.phone)
        if msg is None:
            print("Usage: /pin 10.36 77.97", file=stdout)
            continue
        with sessions() as db:
            process_inbound(db, msg, channel, deps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
