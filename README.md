# Vilai (விலை)

A WhatsApp bot that tells Tamil Nadu farmers which mandi pays the most **after transport and market deductions**, warns about supply gluts, and gives hold-or-sell advice for crops that can be stored. It works by text and voice, in Tamil and English.

The full plan and architecture are in [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md). Working rules for contributors (human or AI) are in [CLAUDE.md](CLAUDE.md).

## Status

Phase 0, the data spike, is in progress. What we've verified about the data sources, the open risks and the steps left are in [docs/PHASE0_DATA.md](docs/PHASE0_DATA.md). The delivery plan is in §9 of the project plan.

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
