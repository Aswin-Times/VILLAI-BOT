# Running Vilai on WhatsApp (Twilio sandbox)

This connects your phone to the bot running on your computer. It takes about 15 minutes. Everything here uses free tiers.

## What you need

- A Twilio account (the free trial is enough)
- [ngrok](https://ngrok.com) (or any tunnel that gives you a public HTTPS URL)
- This repo set up (`uv sync`), and a database: Postgres via `docker compose up -d db`, or a local SQLite file

## 1. Fill in `.env`

Copy `.env.example` to `.env`, then set:

| Variable | Where it comes from |
|---|---|
| `PHONE_HASH_SECRET` | Generate once: `python -c "import secrets; print(secrets.token_hex(32))"`. Keep it stable: changing it forgets everyone's half-finished onboarding. |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | Twilio Console home page |
| `TWILIO_WHATSAPP_FROM` | The sandbox number, `whatsapp:+14155238886` by default |
| `DATABASE_URL` | Postgres URL, or `sqlite:///./vilai-dev.db` |
| `PUBLIC_BASE_URL` | Your ngrok URL (step 3) |

## 2. Prepare the database

```bash
uv run alembic upgrade head
uv run python -m app.data.ingest --sync-reference
```

No real price data yet (Phase 0 needs your data.gov.in key)? For SQLite only, load the made-up demo prices:

```bash
uv run python -m app.data.demo
```

## 3. Start the API and the tunnel

```bash
uv run uvicorn app.main:app --port 8000
```

In a second terminal:

```bash
ngrok http 8000
```

Copy the `https://...ngrok...` URL into `PUBLIC_BASE_URL` in `.env`, then restart uvicorn. Twilio signs each request with the URL it calls, so this must match exactly, or every message gets a 403.

## 4. Point the Twilio sandbox at the bot

1. In the Twilio Console, open **Messaging → Try it out → Send a WhatsApp message**.
2. Under **Sandbox settings**, set **When a message comes in** to `https://<your-ngrok-url>/webhooks/twilio/whatsapp`, method **POST**, and save.
3. On each tester's phone, send the sandbox's `join <word>` code (shown on that page) to the sandbox number.

## 5. Talk to it

Send `hi`. You should get the bilingual welcome, then language, consent, location, crops, and you can ask, for example, `20 quintal thakkali`.

## Try it without WhatsApp

The terminal simulator runs the same pipeline (database, chat logic, templates, engine) without Twilio:

```bash
uv run python -m app.conversation.simulate
```

Type as a farmer would. `/pin 10.36 77.97` sends a location pin. It uses a made-up phone number, so use a dev database.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Twilio shows 403 errors | `PUBLIC_BASE_URL` doesn't match the URL in the sandbox settings, or `TWILIO_AUTH_TOKEN` is wrong |
| Twilio shows 503 | `PHONE_HASH_SECRET` is not set |
| No reply, and the log says `[not sent: no Twilio credentials]` | `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` missing, so replies only go to the log |
| A tester gets nothing at all | Their number hasn't joined the sandbox, or Twilio needs them to send the join code again |
| "No mandi near ... has reported" | No prices in the database for that crop in the last 2 weeks |

## Sandbox limits to design around

- Only numbers that joined the sandbox can talk to it.
- The bot can reply freely only within 24 hours of the farmer's last message. Daily alerts (Phase 4) need pre-approved templates on a production sender.

## Claude intent parsing (optional)

Set `INTENT_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` to parse messages with Claude Haiku, with the rules parser as fallback. Only the message text is sent, never the phone number. To measure it on the golden set (about 70 API calls, a few cents):

```bash
RUN_LLM_EVALS=1 uv run pytest tests/conversation/test_llm_golden.py -s
```

Before the pilot, the consent message should say that message text is processed by an AI service (see D-010 in DECISIONS.md).

## Phase 2 exit checklist

- [ ] 5 friends complete onboarding on WhatsApp
- [ ] Each gets correct advice by text (check `recommendations` against the price data)
- [ ] Golden set ≥ 90% (rules: CI; Claude: the command above)
- [ ] A native Tamil speaker has reviewed `app/conversation/templates/ta.yaml` and the Tamil in the golden set
