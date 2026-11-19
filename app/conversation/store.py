"""Load and save chat sessions.

Before consent a conversation row holds only the phone hash, the state and the
language. The farmer row (with the real number), crops and location are written
only once the session is consented.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from app.conversation.machine import Session as ChatSession
from app.models import Commodity, Conversation, Farmer, FarmerCrop


def load_session(db: Db, phone_hash: str) -> tuple[ChatSession, int | None]:
    conv = db.get(Conversation, phone_hash)
    if conv is None:
        return ChatSession(), None
    farmer = db.get(Farmer, conv.farmer_id) if conv.farmer_id else None
    slots = conv.slots or {}
    chat = ChatSession(
        state=conv.state,
        language=conv.language,
        consented=farmer is not None,
        pending=dict(slots.get("pending") or {}),
        last_disclaimer=slots.get("last_disclaimer"),
    )
    if farmer is not None:
        chat.lat, chat.lon, chat.place = farmer.lat, farmer.lon, farmer.place_name
        chat.crops = list(
            db.scalars(
                select(Commodity.code)
                .join(FarmerCrop, FarmerCrop.commodity_id == Commodity.id)
                .where(FarmerCrop.farmer_id == farmer.id)
                .order_by(Commodity.code)
            )
        )
    return chat, farmer.id if farmer else None


def save_session(
    db: Db, phone_hash: str, phone_e164: str, chat: ChatSession, now: datetime
) -> Farmer | None:
    conv = db.get(Conversation, phone_hash)
    if chat == ChatSession():  # the farmer declined: forget the conversation entirely
        if conv is not None:
            db.delete(conv)
        return None
    if conv is None:
        conv = Conversation(phone_hash=phone_hash)
        db.add(conv)
    conv.state, conv.language = chat.state, chat.language
    if not chat.consented:
        conv.slots = {}
        return None

    farmer = db.get(Farmer, conv.farmer_id) if conv.farmer_id else None
    if farmer is None:
        farmer = db.scalars(select(Farmer).where(Farmer.phone_e164 == phone_e164)).one_or_none()
    if farmer is None:
        farmer = Farmer(phone_e164=phone_e164, language=chat.language or "en", consent_at=now)
        db.add(farmer)
        db.flush()
    farmer.language = chat.language or farmer.language
    farmer.lat, farmer.lon, farmer.place_name = chat.lat, chat.lon, chat.place
    _set_crops(db, farmer, chat.crops)
    conv.farmer_id = farmer.id
    conv.slots = {"pending": chat.pending, "last_disclaimer": chat.last_disclaimer}
    return farmer


def _set_crops(db: Db, farmer: Farmer, codes: list[str]) -> None:
    wanted = (
        set(db.scalars(select(Commodity.id).where(Commodity.code.in_(codes)))) if codes else set()
    )
    current = {fc.commodity_id: fc for fc in farmer.crops}
    for commodity_id, fc in current.items():
        if commodity_id not in wanted:
            farmer.crops.remove(fc)
    for commodity_id in wanted - current.keys():
        farmer.crops.append(FarmerCrop(farmer_id=farmer.id, commodity_id=commodity_id))
