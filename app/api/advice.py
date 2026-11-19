"""POST /v1/advice: where to sell, used by the bot, tests and the dashboard."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_today
from app.engine.units import UnitError
from app.schemas.advice import AdviceRequest, AdviceResponse
from app.services.advice import UnknownCommodityError, get_advice

router = APIRouter(prefix="/v1", tags=["advice"])


@router.post("/advice")
def post_advice(
    req: AdviceRequest,
    session: Annotated[Session, Depends(get_session)],
    today: Annotated[date, Depends(get_today)],
) -> AdviceResponse:
    try:
        resp = get_advice(session, req, today)
    except UnknownCommodityError as e:
        raise HTTPException(status_code=404, detail=f"unknown commodity: {e}") from e
    except UnitError as e:
        raise HTTPException(status_code=422, detail=f"unit: {e}") from e
    session.commit()
    return resp
