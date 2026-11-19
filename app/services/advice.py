"""Advice service: load data from the DB, run the engine, log the result.

All numbers in the response come from `app.engine`; this module only moves
data in and out and rounds for display.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import isfinite
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.normalize import normalise_name
from app.data.reference import load_transport_rates
from app.engine.advice import advise
from app.engine.glut import DEFAULT_GLUT_THRESHOLDS, GlutSignal, GlutThresholds
from app.engine.ranking import DEFAULT_MAX_AGE_DAYS, MarketQuote, RankedMarket
from app.engine.transport import Vehicle
from app.engine.units import to_quintals
from app.models import ArrivalRow, Commodity, Market, PriceRow, Recommendation
from app.schemas.advice import AdviceRequest, AdviceResponse, GlutOut, MarketOption


class UnknownCommodityError(LookupError):
    pass


def default_fleet() -> tuple[Vehicle, ...]:
    return tuple(
        Vehicle(v.code, v.capacity_quintals, v.rate_per_km, v.min_charge)
        for v in load_transport_rates()
    )


def resolve_commodity(session: Session, text: str) -> Commodity | None:
    key = normalise_name(text)
    for c in session.scalars(select(Commodity)):
        if key in {c.code, normalise_name(c.name_en), *c.synonyms}:
            return c
    return None


def latest_quotes(
    session: Session, commodity_id: int, today: date, lookback_days: int = DEFAULT_MAX_AGE_DAYS
) -> list[MarketQuote]:
    """Latest clean price day per active market; several varieties that day are combined."""
    rows = session.execute(
        select(PriceRow, Market)
        .join(Market, PriceRow.market_id == Market.id)
        .where(
            PriceRow.commodity_id == commodity_id,
            PriceRow.obs_date.between(today - timedelta(days=lookback_days), today),
            Market.active.is_(True),
        )
    ).all()
    by_market: dict[int, tuple[Market, list[PriceRow]]] = {}
    for price, market in rows:
        if price.quality_flags or price.modal_price is None:
            continue
        by_market.setdefault(market.id, (market, []))[1].append(price)

    quotes: list[MarketQuote] = []
    for market, prices in by_market.values():
        latest = max(p.obs_date for p in prices)
        day = [p for p in prices if p.obs_date == latest]
        mins = [p.min_price for p in day if p.min_price is not None]
        maxs = [p.max_price for p in day if p.max_price is not None]
        quotes.append(
            MarketQuote(
                market_code=market.code,
                market_name=market.name,
                lat=market.lat,
                lon=market.lon,
                deductions_pct=market.deductions_pct,
                obs_date=latest,
                min_price=min(mins) if mins else None,
                modal_price=median(p.modal_price for p in day if p.modal_price is not None),
                max_price=max(maxs) if maxs else None,
            )
        )
    return quotes


def arrivals_by_market(
    session: Session, commodity_id: int, start: date, end: date
) -> dict[str, dict[date, float]]:
    rows = session.execute(
        select(ArrivalRow.obs_date, ArrivalRow.arrivals_tonnes, Market.code)
        .join(Market, ArrivalRow.market_id == Market.id)
        .where(ArrivalRow.commodity_id == commodity_id, ArrivalRow.obs_date.between(start, end))
    ).all()
    out: dict[str, dict[date, float]] = defaultdict(dict)
    for day, tonnes, code in rows:
        out[code][day] = tonnes
    return dict(out)


def get_advice(
    session: Session,
    req: AdviceRequest,
    today: date,
    fleet: tuple[Vehicle, ...] | None = None,
    glut_thresholds: GlutThresholds = DEFAULT_GLUT_THRESHOLDS,
    farmer_id: int | None = None,
) -> AdviceResponse:
    commodity = resolve_commodity(session, req.commodity)
    if commodity is None:
        raise UnknownCommodityError(req.commodity)
    qty_q = to_quintals(req.quantity, req.unit, commodity.pack_weights_kg)

    quotes = latest_quotes(session, commodity.id, today)
    arrivals: dict[str, dict[date, float]] = {}
    if quotes:
        start = min(q.obs_date for q in quotes) - timedelta(days=glut_thresholds.window_days)
        arrivals = arrivals_by_market(session, commodity.id, start, today)

    advice = advise(
        quotes,
        arrivals,
        qty_q=qty_q,
        farmer_lat=req.lat,
        farmer_lon=req.lon,
        fleet=fleet or default_fleet(),
        today=today,
        rate_per_km_override=req.rate_per_km,
        glut_thresholds=glut_thresholds,
    )
    ranking = advice.ranking
    warnings = list(advice.warnings)
    if not commodity.mapping_verified:
        warnings.append("commodity_mapping_unverified")

    result = {
        "commodity_code": commodity.code,
        "quantity_quintals": round(qty_q, 3),
        "data_as_of": ranking.data_as_of,
        "best_market_code": ranking.best.quote.market_code if ranking.best else None,
        "nearest_market_code": ranking.nearest.quote.market_code if ranking.nearest else None,
        "extra_vs_nearest": _money(ranking.extra_vs_nearest),
        "options": [_option(o, advice.gluts[o.quote.market_code]) for o in ranking.options],
        "regional_glut": advice.regional.flagged,
        "excluded": ranking.excluded,
        "warnings": warnings,
    }
    rec = Recommendation(
        farmer_id=farmer_id,
        request=req.model_dump(mode="json"),
        result={},
        data_as_of=ranking.data_as_of,
    )
    session.add(rec)
    session.flush()  # assigns rec.id
    resp = AdviceResponse.model_validate({"recommendation_id": rec.id, **result})
    rec.result = resp.model_dump(mode="json")
    return resp


def _money(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def _finite(x: float | None, digits: int = 1) -> float | None:
    return round(x, digits) if x is not None and isfinite(x) else None


def _option(o: RankedMarket, glut: GlutSignal) -> MarketOption:
    p = o.price
    return MarketOption(
        market_code=o.quote.market_code,
        market_name=o.quote.market_name,
        obs_date=o.quote.obs_date,
        stale=o.stale,
        distance_km=round(p.distance_km, 1),
        modal_price=round(p.gross, 2),
        deductions_per_q=round(p.deductions, 2),
        transport_per_q=round(p.transport, 2),
        net_per_q=round(p.net, 2),
        net_per_q_low=round(p.net_low, 2),
        net_per_q_high=round(p.net_high, 2),
        total_net=round(p.total, 2),
        glut=GlutOut(
            flagged=glut.flagged,
            arrivals_tonnes=glut.arrivals,
            baseline_tonnes=_finite(glut.baseline),
            pct_above_normal=_finite(glut.pct_above_normal),
            reason=glut.reason,
        ),
    )
