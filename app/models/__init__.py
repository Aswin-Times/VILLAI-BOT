"""SQLAlchemy tables for reference data, prices and the advice audit log.

Prices are ₹/quintal and arrivals are tonnes, always. Farmer and conversation
tables arrive with Phase 2.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = JSON().with_variant(JSONB(), "postgresql")
Money = Numeric(12, 2, asdecimal=False)


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    district: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(64), default="Tamil Nadu")
    agmarknet_district: Mapped[str] = mapped_column(String(64))
    lat: Mapped[float]
    lon: Mapped[float]
    agmarknet_names: Mapped[list[str]] = mapped_column(JSONType)
    market_type: Mapped[str] = mapped_column(String(16))
    deductions_pct: Mapped[float]
    active: Mapped[bool] = mapped_column(default=True)
    verified: Mapped[bool] = mapped_column(default=False)


class Commodity(Base):
    __tablename__ = "commodities"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name_en: Mapped[str] = mapped_column(String(64))
    name_ta: Mapped[str] = mapped_column(String(64))
    agmarknet_commodity: Mapped[str] = mapped_column(String(64))
    agmarknet_varieties: Mapped[list[str]] = mapped_column(JSONType, default=list)
    exclude_varieties: Mapped[list[str]] = mapped_column(JSONType, default=list)
    synonyms: Mapped[list[str]] = mapped_column(JSONType)
    storable: Mapped[bool]
    storage_loss_pct_per_week: Mapped[float | None]
    unit: Mapped[str] = mapped_column(String(16), default="quintal")
    pack_weights_kg: Mapped[dict[str, float]] = mapped_column(JSONType, default=dict)
    mapping_verified: Mapped[bool] = mapped_column(default=False)


class PriceRow(Base):
    """One day's price for a market x commodity x variety x grade (₹/quintal)."""

    __tablename__ = "price_observations"
    __table_args__ = (
        UniqueConstraint(
            "obs_date", "market_id", "commodity_id", "variety", "grade", name="uq_price_obs_day"
        ),
        Index("ix_price_obs_lookup", "commodity_id", "market_id", "obs_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    obs_date: Mapped[date] = mapped_column(Date)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"))
    variety: Mapped[str] = mapped_column(String(64))
    grade: Mapped[str] = mapped_column(String(32))
    min_price: Mapped[float | None] = mapped_column(Money)
    max_price: Mapped[float | None] = mapped_column(Money)
    modal_price: Mapped[float | None] = mapped_column(Money)
    source: Mapped[str] = mapped_column(String(32))
    quality_flags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ArrivalRow(Base):
    """One day's arrivals for a market x commodity (tonnes, all varieties together)."""

    __tablename__ = "arrivals"
    __table_args__ = (
        UniqueConstraint("obs_date", "market_id", "commodity_id", name="uq_arrivals_day"),
        Index("ix_arrivals_lookup", "commodity_id", "market_id", "obs_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    obs_date: Mapped[date] = mapped_column(Date)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"))
    arrivals_tonnes: Mapped[float] = mapped_column(Numeric(12, 3, asdecimal=False))
    source: Mapped[str] = mapped_column(String(32))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Recommendation(Base):
    """Audit log: every advice result with the request and the data date it used."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    farmer_id: Mapped[int | None]  # FK to farmers arrives with Phase 2
    request: Mapped[dict[str, Any]] = mapped_column(JSONType)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType)
    data_as_of: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType)
