# Vilai (விலை)

A WhatsApp bot that tells Tamil Nadu farmers which mandi pays the most **after transport and market deductions**, warns about supply gluts, and gives hold-or-sell advice for crops that can be stored. It works by text and voice, in Tamil and English.

The full plan and architecture are in [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md). Working rules for contributors (human or AI) are in [CLAUDE.md](CLAUDE.md).

## Status

- **Phase 0 (data spike):** code done; waiting on API keys to run the 5-year backfill and the go/no-go on crops and mandis. Findings and open risks: [docs/PHASE0_DATA.md](docs/PHASE0_DATA.md).
- **Phase 1 (core + engine):** code done. `POST /v1/advice` works end to end on demo data for all four crops; the exit check on real data waits for Phase 0. Engine coverage is 100%.
- **Phase 2 (WhatsApp text bot):** code done: signed Twilio webhook, onboarding with consent, confirm-before-advise, Tamil and English replies, rules parser plus optional Claude Haiku parser. Next: connect the Twilio sandbox and run the 5-friend test, see [docs/WHATSAPP_SETUP.md](docs/WHATSAPP_SETUP.md).

Design choices that differ from the plan are recorded in [docs/DECISIONS.md](docs/DECISIONS.md). The delivery plan is in §9 of the project plan.

## Ground rules

- Every price or number a farmer sees comes from the deterministic engine in `app/engine/`. An LLM only turns the farmer's message into structured fields.
- Every advice reply shows the date of the data it used.
- Nothing about a farmer is stored before they consent.

## Local setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
uv sync
uv run pytest
uv run ruff check . && uv run mypy app
```

Run the API with Postgres in Docker:

```bash
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Without Docker, point `DATABASE_URL` at a local SQLite file (fine for development; production is Postgres):

```bash
DATABASE_URL=sqlite:///./vilai.db uv run alembic upgrade head
```

Tests use a throwaway SQLite database. To run them against Postgres, set `TEST_DATABASE_URL` (CI runs both).

### Try the API without API keys (made-up demo prices)

`app.data.demo` loads **invented** prices for the four pilot crops into a local SQLite file, so you can try the API before real data arrives. Every row is tagged `source="demo"`, and the loader refuses any database that isn't SQLite.

```bash
DATABASE_URL=sqlite:///./vilai-demo.db uv run python -m app.data.demo
DATABASE_URL=sqlite:///./vilai-demo.db uv run uvicorn app.main:app --port 8000
curl -X POST localhost:8000/v1/advice -H "content-type: application/json" \
  -d '{"commodity":"thakkali","quantity":20,"unit":"quintal","lat":10.37,"lon":77.96}'
```

Interactive API docs: http://localhost:8000/docs

### Real data

With `DATAGOV_API_KEY` in `.env`:

```bash
uv run alembic upgrade head
uv run python -m app.data.backfill          # 5 years, pilot districts x crops
uv run python -m app.data.ingest --sync-reference data/raw/datagov/history
uv run python -m app.data.fetch_day         # yesterday; then ingest that file
```
