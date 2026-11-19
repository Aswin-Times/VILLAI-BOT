# Decisions

Short records of choices that aren't obvious from the code or the plan.

**D-001 · One branch per phase.** Work happens on `phase-N-...` branches, pushed after every
verified step. `main` only changes through merges.

**D-002 · Phase 1 started before Phase 0 closed** (approved 19 Nov 2026). Phase 0 is blocked on
API keys. The engine and API are built against fixtures, and real data drops in once the
backfill runs. Phase 1's exit check (`/v1/advice` on real data for all 4 crops) still waits
for Phase 0.

**D-003 · Arrivals get their own table.** The plan put `arrivals_tonnes` on
`price_observations`, but prices come per variety and grade (data.gov.in) while arrivals come
per market and day (CEDA). One column would repeat the same figure on every variety row.
`arrivals(obs_date, market_id, commodity_id)` is unique instead.

**D-004 · The price unique key includes grade.** Agmarknet can report two grades of one
variety on the same day, so the key is `(obs_date, market_id, commodity_id, variety, grade)`.

**D-005 · Uzhavar Sandhai rows are never ranked.** They're retail farmer-to-consumer prices for
small lots. They aren't in the markets seed, and ingestion drops them.

**D-006 · Tests run on SQLite locally and on Postgres 16 in CI.** Docker isn't on the dev
machine. Models use portable types (JSON becomes JSONB on Postgres), and CI runs the whole
suite on both. `TEST_DATABASE_URL` switches the suite to Postgres.

**D-007 · Demo data is quarantined.** `app.data.demo` writes invented prices so the API (and
the Phase 2 bot) can be exercised without API keys. Rows carry `source="demo"`, and the loader
refuses any database that isn't SQLite.

**D-008 · Unverified crop mappings are served with a warning, not hidden.** Small onion and
banana mappings aren't confirmed yet (see PHASE0_DATA.md §4). `/v1/advice` still answers but
adds `commodity_mapping_unverified`; the bot must not present those prices as confirmed.
