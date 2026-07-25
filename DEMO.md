# Local demo guide

This is the canonical local startup guide for the backend, frontend, optional MongoDB,
Layer 1, sanitized demo data, and the allowlisted Telegram bridge.

## Fastest start: memory + fake analyzer

This mode needs no password and no database. From `backend/`:

```powershell
uv sync --dev
uv run uvicorn app.demo:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`. The root redirects to `/demo/`.

In a second terminal, seed four sanitized chats and wait for their analysis jobs:

```powershell
Set-Location backend
uv run python scripts/seed_demo.py
```

The command prints the exact demo URL. The frontend discovers chats automatically after you
enter the account ID; the seed command uses account `900001` by default.

Memory mode loses its messages when Uvicorn stops. That is expected.

## Connect Telegram from the frontend

The combined app also supports concurrent TDLib user sessions. Keep
`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TDJSON_PATH`, and
`TDLIB_DATABASE_ENCRYPTION_KEY` in the ignored root `.env`, start the combined
app, and select **Connect Telegram**. Complete the phone, code, and optional
two-step-verification prompts.

Each login has an isolated encrypted TDLib directory under
`telegram/.tdlib/web`. A local SQLite registry stores only opaque ownership and
account metadata; authentication codes and passwords are never stored. The
browser owns sessions through an HttpOnly, SameSite=Strict cookie. Connected
mode imports up to 100 recent text messages from Saved Messages and then
accepts only new Saved Messages updates. Its protected read endpoints continue
using the existing two-second frontend polling.

**Log out** calls Telegram's `logOut`, closes that TDLib client, and removes its
local session directory. Keep the service bound to `127.0.0.1`; this milestone
does not provide remote-user application authentication.

## Run the installed Layer 1

Copy the safe example configuration once:

```powershell
Set-Location backend
Copy-Item .env.example .env
```

Edit `backend/.env` and change only:

```dotenv
TECH4CITY_ANALYZER=layer1
```

Then install the optional model runtime and start the combined app:

```powershell
uv sync --dev --extra ml
uv run uvicorn app.demo:app --host 127.0.0.1 --port 8765
```

Run `uv run python scripts/seed_demo.py` in another terminal. The first model startup can take
longer than fake mode. The displayed raw labels and continuous scores are integration output,
not an accuracy or calibration claim.

The configured adapter references a gated base model. Set an approved `HF_TOKEN` only in the
ignored `backend/.env` if the base weights are not already cached. Never paste or commit it.

## Add MongoDB persistence

MongoDB is optional. You choose the local password; the project does not generate or retrieve
one. Use letters, numbers, `_`, or `-` so the value can be placed in the URI without escaping.

1. Copy `backend/.env.example` to `backend/.env` if needed.
2. Uncomment the MongoDB block.
3. Replace both `replace-with-your-own-local-password` placeholders with the same password.
4. Start Docker Desktop.
5. From `backend/`, run:

```powershell
docker compose up -d
docker compose ps
uv run uvicorn app.demo:app --host 127.0.0.1 --port 8765
```

`docker compose ps` should show MongoDB as healthy. Check the active configuration at
`http://127.0.0.1:8765/health`; its `storage` field should be `mongodb`.

Stop the app with Ctrl+C. Stop MongoDB without deleting stored data:

```powershell
docker compose stop
```

Do not run `docker compose down -v` unless you intentionally want to delete the local database.

## Run the Telegram bridge safely

The bridge is default-deny. It refuses to start until at least one Telegram chat ID is explicitly
allowed. Start with Saved Messages, whose chat ID is normally the same as your Telegram account
ID.

In the ignored root `.env`:

```dotenv
TECH4CITY_BACKEND_URL=http://127.0.0.1:8765
TECH4CITY_BRIDGE_ALLOWED_CHAT_IDS=your_saved_messages_chat_id
```

Multiple approved test chats use a comma-separated list:

```dotenv
TECH4CITY_BRIDGE_ALLOWED_CHAT_IDS=123456,-1009876543210
```

With the combined app already running, start the bridge from the repository root:

```powershell
.\.venv\Scripts\python.exe -m telegram.bridge
```

Only new nonblank text messages from the allowlist are forwarded. Other private chats are
ignored and message content is not logged. The current API is unauthenticated, so keep all
services bound to `127.0.0.1` and use low-sensitivity test chats only.

## What runs where

- `app.demo:app`: backend API plus the static frontend at `/demo/`.
- `app.main:app`: backend API only; `/` intentionally has no frontend there.
- `TECH4CITY_STORAGE=memory`: no database, fastest disposable demo.
- `TECH4CITY_STORAGE=mongodb`: persistent messages, jobs, and analysis runs.
- `TECH4CITY_ANALYZER=fake`: quick software-contract testing.
- `TECH4CITY_ANALYZER=layer1`: installed local classifier through the same worker contract.

The frontend remains read-only and polls every two seconds. Chat discovery is derived from stored
messages. Layer 2, WebSockets, authentication, media, edits, deletes, and history backfill are not
part of this milestone.

## Verify

From `backend/`:

```powershell
uv run pytest -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
```

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
node --check frontend/app.js
```
