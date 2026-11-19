"""Reference data and price history."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_today
from app.models import Commodity, Market, PriceRow
from app.services.advice import resolve_commodity

router = APIRouter(prefix="/v1", tags=["reference"])


class MarketOut(BaseModel):
    code: str
    name: str
    district: str
    lat: float
    lon: float
    market_type: str
    deductions_pct: float
    verified: bool


class CommodityOut(BaseModel):
    code: str
    name_en: str
    name_ta: str
    storable: bool
    mapping_verified: bool


class PriceOut(BaseModel):
    obs_date: date
    market_code: str
    variety: str
    grade: str
    min_price: float | None
    modal_price: float | None
    max_price: float | None
    quality_flags: list[str]


@router.get("/markets")
def list_markets(session: Annotated[Session, Depends(get_session)]) -> list[MarketOut]:
    markets = session.scalars(select(Market).where(Market.active.is_(True)).order_by(Market.code))
    return [MarketOut.model_validate(m, from_attributes=True) for m in markets]


@router.get("/commodities")
def list_commodities(session: Annotated[Session, Depends(get_session)]) -> list[CommodityOut]:
    rows = session.scalars(select(Commodity).order_by(Commodity.code))
    return [CommodityOut.model_validate(c, from_attributes=True) for c in rows]


@router.get("/prices")
def price_history(
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(get_today)],
    commodity: str,
    market: str | None = None,
    days: Annotated[int, Query(ge=1, le=3650)] = 30,
) -> list[PriceOut]:
    c = resolve_commodity(session, commodity)
    if c is None:
        raise HTTPException(status_code=404, detail=f"unknown commodity: {commodity}")
    query = (
        select(PriceRow, Market.code)
        .join(Market, PriceRow.market_id == Market.id)
        .where(
            PriceRow.commodity_id == c.id,
            PriceRow.obs_date.between(today - timedelta(days=days), today),
        )
        .order_by(PriceRow.obs_date, Market.code, PriceRow.variety)
    )
    if market:
        query = query.where(Market.code == market)
    return [
        PriceOut(
            obs_date=p.obs_date,
            market_code=code,
            variety=p.variety,
            grade=p.grade,
            min_price=p.min_price,
            modal_price=p.modal_price,
            max_price=p.max_price,
            quality_flags=p.quality_flags,
        )
        for p, code in session.execute(query)
    ]
