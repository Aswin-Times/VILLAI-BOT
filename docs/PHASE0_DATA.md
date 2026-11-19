# Phase 0: data spike findings

Status as of 19 Nov 2026. Checked against live APIs on 18–19 Nov 2026.

**Short version:** prices are available and scriptable. Arrivals (needed for glut
warnings) aren't in the price API, and come from CEDA's API instead. Most
Tamil Nadu rows come from retail farmers' markets that we must exclude.
**Small onion may not be reported under the name we expected.** Phase 0 can't
close until we have our own API keys and have run the backfill.

## 1. Prices: data.gov.in OGD API ✅ works

The plan's warning that "an API doesn't exist" is out of date. Both resources respond:

| Resource | ID | Use |
|---|---|---|
| Current Daily Price of Various Commodities from Various Markets (Mandi) | `9ef84268-d588-465a-a308-a864a43d0070` | Today only. Filters: `state.keyword`, `district`, `market`, `commodity`, `variety`, `grade`. Prices are numbers. |
| **Variety-wise Daily Market Prices Data of Commodity** | `35985678-0d79-46b4-9ed6-6f13308a1d24` | **What we use.** History back to the 2000s (7.2M Tamil Nadu rows). Filters: `State`, `District`, `Commodity`, `Arrival_Date`. Prices arrive as strings. |

- Fields (variety-wise): `Arrival_Date` (`dd/mm/yyyy`), `State`, `District`, `Market`,
  `Commodity`, `Commodity_Code`, `Variety`, `Grade`, `Min_Price`, `Max_Price`, `Modal_Price`.
- Units: ₹/quintal.
- **No arrival quantities** in either resource.
- The public sample key returns at most **10 rows per request** and gets rate-limited
  (HTTP 429) quickly. **We need our own free key** for real pulls.
- Efficient backfill: filter by `District` + `Commodity` with no date filter to get all
  history for that pair in a few pages. That's ~36 district × crop pairs, not ~7,300 day requests.
- The resource is updated daily (last update seen 18 Nov 2026 23:34 UTC). 18 Nov already
  had 185 Tamil Nadu tomato rows by the morning of 19 Nov.

## 2. Arrivals: CEDA Ashoka API ⚠ needs a key, unit to confirm

- **Agmarknet 2.0** (agmarknet.gov.in) has a "Daily Price and Arrival Report", but it's
  behind a **CAPTCHA**. We won't automate around that. It's usable only for manual
  CSV exports (`agmarknet_csv` adapter, later).
- **CEDA Ashoka Agri Market API** (`https://api.ceda.ashoka.edu.in/v1`, Bearer token, free
  registration) has:
  - `GET /agmarknet/commodities`, `GET /agmarknet/geographies`
  - `POST /agmarknet/markets` (by commodity, state, district, `indicator: price|quantity`)
  - `POST /agmarknet/prices`: `date, market_id, min_price, max_price, modal_price`
  - `POST /agmarknet/quantities`: `date, market_id, quantity`
  - Date-range queries (`from_date`, `to_date`), state/district/market filters.
- To confirm once we have a key: the **unit of `quantity`** (likely tonnes), whether
  responses are per variety or aggregated (the schema has no variety field), and how
  far back Tamil Nadu market quantities go.

## 3. Retail farmers' markets: must be excluded ⚠

Most recent Tamil Nadu rows come from **Uzhavar Sandhai** (e.g. `Palani(Uzhavar Sandhai )`).
These are state-run farmer-to-consumer markets: retail prices, small lots, ID-card stalls.
A farmer can't sell 20 quintals there, so ranking them would be wrong advice.
Wholesale markets appear as plain names or with an `RM` (Regulated Market) suffix,
e.g. `Udumalpettai RM`. `app/data/normalize.is_uzhavar_sandhai()` detects them.

## 4. Crop mapping

| Crop | Agmarknet commodity | What we saw | Status |
|---|---|---|---|
| Tomato | `Tomato` (code 78) | Varieties Deshi, Hybrid, Local, Other. 18 Nov modal ₹2,750–4,300/q (mostly Uzhavar Sandhai). | ✅ |
| **Small onion** | `Onion` (code 23)? | **Only `Bellary` (big onion) rows** in Dindigul (18 Nov), Perambalur (2024) and Tiruppur (2026). `Small Onion` as a commodity returned 0 rows. Older Dindigul rows (2006–12) have varieties `Local`, `Medium`, `Onion`. | ❌ **Unconfirmed: biggest go/no-go risk** |
| Turmeric | `Turmeric` | Varieties `Finger` and `Bulb`, priced differently. Reported at Erode and Namagiripettai. | ✅ |
| Banana | `Banana` (code 19) | Varieties Poovan, Red Banana, ... `Udumalpettai RM` reports it. Raw banana is a separate commodity, `Banana - Green` (code 90). | ⚠ Units to confirm per market |

## 5. Market names

Names drift over time: Oddanchatram appears as **`Oddunchairum`** in 2012 data. The seed
file `app/data/seed/markets.csv` holds aliases per market. Matching must be exact after
whitespace normalisation, never substring: `Palani` ≠ `Palani(Uzhavar Sandhai )`.

Oddanchatram, the biggest vegetable market in the pilot area, **didn't report on 18 Nov**.
The coverage report will show how regularly it reports.

## 6. What's in the repo now

| Piece | Command / path |
|---|---|
| Source adapter (paging, retries, 429 back-off, schema-drift check) | `app/data/sources/datagov.py` |
| Fetch yesterday's prices (India time) | `uv run python -m app.data.fetch_day` |
| 5-year backfill, resumable | `uv run python -m app.data.backfill` |
| Coverage report for go/no-go | `uv run python -m app.data.coverage --write docs/coverage.md` |
| Reference data | `app/data/seed/` (crops, 15 candidate mandis, vehicle rates) |

Seed values marked `verified: false` are placeholders: market coordinates are approximate
town centres, deductions (8% commission markets, 1% regulated) and vehicle rates are
guesses to replace with local quotes (plan §12 Q2–Q4).

## 7. To close Phase 0

1. Get a free **data.gov.in API key** (data.gov.in → sign up → My Account → API key) and
   put it in `.env` as `DATAGOV_API_KEY`.
2. Register for a free **CEDA API key** (ceda.ashoka.edu.in → Data Portal API) and put it
   in `.env` as `CEDA_API_KEY`.
3. Run `uv run python -m app.data.backfill`, then `uv run python -m app.data.coverage --write docs/coverage.md`.
4. With the coverage table: find small onion's real name/variety (or drop it), confirm which
   wholesale mandis report each crop regularly, and drop the rest.
5. Add a CEDA adapter for arrivals and confirm the quantity unit.
6. Go/no-go on crops and mandis.
