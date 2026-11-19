"""Farmer data tables: deleting a farmer removes everything about them."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.ingest import sync_reference
from app.models import Commodity, Conversation, Farmer, FarmerCrop, MessageLog


def test_deleting_a_farmer_removes_their_crops_messages_and_conversation_link(
    session: Session,
) -> None:
    sync_reference(session)
    tomato = session.scalars(select(Commodity).where(Commodity.code == "tomato")).one()
    farmer = Farmer(phone_e164="+919876543210", language="ta", consent_at=datetime.now(UTC))
    session.add(farmer)
    session.flush()
    session.add_all(
        [
            FarmerCrop(farmer_id=farmer.id, commodity_id=tomato.id),
            MessageLog(farmer_id=farmer.id, direction="in", kind="text", body="vanakkam"),
            Conversation(phone_hash="h" * 64, farmer_id=farmer.id, state="idle", slots={}),
        ]
    )
    session.commit()

    session.delete(farmer)
    session.commit()

    assert session.scalar(select(func.count()).select_from(FarmerCrop)) == 0
    assert session.scalar(select(func.count()).select_from(MessageLog)) == 0
    assert session.scalar(select(func.count()).select_from(Conversation)) == 0


def test_conversation_can_exist_before_consent_without_a_farmer(session: Session) -> None:
    session.add(Conversation(phone_hash="a" * 64, state="lang", slots={}))
    session.commit()

    conv = session.get(Conversation, "a" * 64)
    assert conv is not None
    assert conv.farmer_id is None
