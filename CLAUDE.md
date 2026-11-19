# Vilai — WhatsApp market advisor for farmers

Full plan and architecture: `docs/PROJECT_PLAN.md`. Read it before starting any phase.

## What this is
A WhatsApp bot (Twilio) that tells Tamil Nadu farmers which mandi pays the most **after transport and deductions**, warns about supply gluts, and gives hold/sell advice for storable crops. Text and voice, in Tamil and English.

## Non-negotiable rules
- **Never let an LLM produce prices or numbers shown to farmers.** The LLM only parses intent into JSON. Replies are templates filled from `app/engine/` output.
- Every advice reply shows the date of the data it used.
- The engine (`app/engine/`) is pure, deterministic and fully unit-tested. No network calls inside it.
- Always confirm crop + quantity + location with the farmer before giving advice.
- All prices are stored as ₹/quintal and arrivals as tonnes; normalise at ingestion.
- Don't store farmer data before consent. Never log full phone numbers in plain text.

## Stack
Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 + Alembic · PostgreSQL · pandas/statsmodels (LightGBM later) · Twilio WhatsApp · Sarvam AI (Saaras STT, Bulbul TTS) · Cloudflare R2 · APScheduler · pytest/ruff/mypy · Next.js dashboard (later).

## Commands
- `docker compose up -d db` — local Postgres
- `uvicorn app.main:app --reload` — run API
- `alembic upgrade head` — migrate
- `pytest` · `ruff check .` · `mypy app`

## Working style
- Build phase by phase as listed in `docs/PROJECT_PLAN.md` §9; don't start a phase before the previous exit criteria pass.
- Write tests first for engine and conversation logic.
- Keep source adapters, channels, STT/TTS and intent parsers behind interfaces so they can be swapped.
- Secrets only via `.env` (see `.env.example`); never commit them.
