"""data.gov.in OGD adapter for Agmarknet daily mandi prices.

Uses the "Variety-wise Daily Market Prices Data of Commodity" resource, which
accepts an exact `Arrival_Date` filter and holds history back to the 2000s.
It has prices only (₹/quintal), no arrival quantities.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any

import httpx

from app.data.sources.base import DataSourceError, PriceObservation, SchemaDriftError

BASE_URL = "https://api.data.gov.in/resource"
VARIETY_WISE_RESOURCE = "35985678-0d79-46b4-9ed6-6f13308a1d24"
REQUIRED_FIELDS = (
    "Arrival_Date",
    "State",
    "District",
    "Market",
    "Commodity",
    "Variety",
    "Grade",
    "Min_Price",
    "Max_Price",
    "Modal_Price",
)
RETRYABLE = (httpx.TimeoutException, httpx.TransportError)
RETRY_STATUS = {429, 502, 503, 504}


def _price(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_record(rec: dict[str, Any], source: str = "datagov") -> PriceObservation:
    return PriceObservation(
        obs_date=datetime.strptime(rec["Arrival_Date"], "%d/%m/%Y").date(),
        state=rec["State"],
        district=rec["District"],
        market=rec["Market"],
        commodity=rec["Commodity"],
        variety=rec["Variety"],
        grade=rec["Grade"],
        min_price=_price(rec.get("Min_Price")),
        max_price=_price(rec.get("Max_Price")),
        modal_price=_price(rec.get("Modal_Price")),
        source=source,
    )


class DataGovSource:
    name = "datagov"

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        *,
        resource_id: str = VARIETY_WISE_RESOURCE,
        page_size: int = 1000,
        max_attempts: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=60)
        self._url = f"{BASE_URL}/{resource_id}"
        self._page_size = page_size
        self._max_attempts = max_attempts
        self._sleep = sleep

    def fetch(
        self, *, day: date, commodities: Sequence[str], state: str = "Tamil Nadu"
    ) -> list[PriceObservation]:
        out: list[PriceObservation] = []
        for commodity in commodities:
            filters = {
                "filters[State]": state,
                "filters[Commodity]": commodity,
                "filters[Arrival_Date]": day.strftime("%d/%m/%Y"),
            }
            out.extend(self._fetch_all(filters))
        return out

    def fetch_history(
        self, *, district: str, commodity: str, state: str = "Tamil Nadu"
    ) -> list[PriceObservation]:
        """Every row for one district and commodity, across all dates."""
        filters = {
            "filters[State]": state,
            "filters[District]": district,
            "filters[Commodity]": commodity,
        }
        return self._fetch_all(filters)

    def _fetch_all(self, filters: dict[str, str]) -> list[PriceObservation]:
        out: list[PriceObservation] = []
        offset = 0
        while True:
            payload = self._get_page(filters, offset)
            _check_schema(payload)
            records = payload.get("records") or []
            out.extend(parse_record(r) for r in records)
            # Step by rows actually returned: some keys cap pages below `limit`.
            offset += len(records)
            if not records or offset >= int(payload.get("total", 0)):
                return out

    def _get_page(self, filters: dict[str, str], offset: int) -> dict[str, Any]:
        params = {
            "api-key": self._api_key,
            "format": "json",
            "limit": str(self._page_size),
            "offset": str(offset),
            **filters,
        }
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = self._client.get(self._url, params=params)
            except RETRYABLE as e:
                last_error = e
                self._sleep(2.0 * (attempt + 1))
                continue
            if resp.status_code in RETRY_STATUS:
                last_error = DataSourceError(f"HTTP {resp.status_code}")
                self._sleep(5.0 * (attempt + 1))
                continue
            if resp.status_code != 200:
                # Never include the URL: it carries the API key.
                raise DataSourceError(f"data.gov.in returned HTTP {resp.status_code}")
            data: dict[str, Any] = resp.json()
            return data
        raise DataSourceError(
            f"data.gov.in unreachable after {self._max_attempts} attempts "
            f"({type(last_error).__name__})"
        )


def _check_schema(payload: dict[str, Any]) -> None:
    fields = {f.get("id") for f in payload.get("field", [])}
    missing = [f for f in REQUIRED_FIELDS if f not in fields]
    if missing:
        raise SchemaDriftError(f"data.gov.in response is missing fields: {', '.join(missing)}")
