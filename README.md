# tech4city

Local FastAPI application for ingesting Telegram text messages, running queued analysis, and
reviewing conversations through a build-free web interface. The default mode is entirely local:
in-memory storage with a deterministic fake analyzer.

## Prerequisites

The documented workflow targets 64-bit Windows and PowerShell. Install:

- Git.
- Python 3.11 or newer (`python --version`).
- PowerShell 5.1 or newer.

Docker Desktop is needed only for MongoDB persistence. Node.js is optional and is used only for
the frontend JavaScript syntax check. Connecting a real Telegram account additionally requires the
native tools listed in [the TDLib guide](README-TDLIB.md#prerequisites).

## First-time setup

From the repository root:

```powershell
python -m pip install "uv>=0.11,<1"
python -m uv sync --locked --dev
```

This creates `.venv` from the checked-in `uv.lock` and installs the application, Telegram Python
utilities, and development tools. The default mode needs no `.env`, password, database, model
download, or API key.

## Quick start

Start the combined backend and frontend:

```powershell
.\scripts\start_demo.ps1
```

Open `http://127.0.0.1:8765/`; the root redirects to `/demo/`.

In a second terminal, seed four sanitized chats and wait for their analysis jobs:

```powershell
.\.venv\Scripts\python.exe backend\scripts\seed_demo.py
```

The command prints the exact demo URL and uses account `900001` by default. Enter that account ID
in the frontend. Memory mode loses its messages when Uvicorn stops.

For the backend API without the frontend, run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the API or `http://127.0.0.1:8000/health` for the active
storage and analyzer configuration.

## Optional integrations

### Connect Telegram from the frontend

First [build TDLib and configure Telegram credentials](README-TDLIB.md). Keep
`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TDJSON_PATH`, and
`TDLIB_DATABASE_ENCRYPTION_KEY` in the ignored root `.env`. Start the combined application,
select **Connect Telegram**, and complete the phone, code, and optional two-step-verification
prompts.

Each login uses an isolated encrypted TDLib directory under `telegram/.tdlib/web`. A local SQLite
registry stores only opaque ownership and account metadata; authentication codes and passwords
are never stored. The browser owns sessions through an HttpOnly, SameSite=Strict cookie.
Connected mode imports up to 100 recent text messages from Saved Messages and then accepts only
new Saved Messages updates.

**Log out** calls Telegram's `logOut`, closes that TDLib client, and removes its local session
directory. Keep the service bound to `127.0.0.1`; this application does not provide remote-user
authentication.

### Run Layer 1

Copy the safe backend configuration once:

```powershell
Copy-Item backend\.env.example backend\.env
```

Edit `backend/.env` and set:

```dotenv
TECH4CITY_ANALYZER=layer1
```

Install the optional model runtime and start the application:

```powershell
python -m uv sync --locked --dev --extra ml
.\scripts\start_demo.ps1
```

Run `.\.venv\Scripts\python.exe backend\scripts\seed_demo.py` in another terminal. The tracked
PEFT adapter references the gated `Roblox/roblox-pii-classifier` base model. Set an approved
`HF_TOKEN` only in the ignored `backend/.env` if the base weights are not cached. Raw labels and
continuous scores are integration output, not an accuracy or calibration claim.

### Add MongoDB persistence

Choose a local password containing letters, numbers, `_`, or `-`; the project does not generate
one.

1. Copy `backend/.env.example` to `backend/.env` if needed.
2. Uncomment the MongoDB block.
3. Replace both password placeholders with the same password.
4. Start Docker Desktop.
5. From the repository root, run:

```powershell
docker compose -f backend\compose.yaml up -d
docker compose -f backend\compose.yaml ps
.\scripts\start_demo.ps1
```

`docker compose -f backend\compose.yaml ps` should show MongoDB as healthy. Confirm that
`http://127.0.0.1:8765/health` reports `"storage": "mongodb"`.

Stop MongoDB without deleting stored data:

```powershell
docker compose -f backend\compose.yaml stop
```

Start it again with `docker compose -f backend\compose.yaml start`.
`docker compose -f backend\compose.yaml down` removes the container but keeps the named volume.
Adding `-v` permanently deletes the local database.

### Run the Telegram bridge

The bridge is default-deny and refuses to start without an explicitly allowed chat. Complete the
[TDLib setup](README-TDLIB.md), then add the backend target and an allowlist to the ignored root
`.env`. Start with Saved Messages, whose chat ID is normally the Telegram account ID:

```dotenv
TECH4CITY_BACKEND_URL=http://127.0.0.1:8765
TECH4CITY_BRIDGE_ALLOWED_CHAT_IDS=your_saved_messages_chat_id
```

Multiple approved test chats use a comma-separated list. With the combined application already
running, start the bridge in another terminal:

```powershell
.\.venv\Scripts\python.exe -m telegram.bridge
```

Only new nonblank text messages from the allowlist are forwarded. Other chats are ignored and
message content is not logged. Transient failures are retried in memory in delivery order, but a
bridge crash can lose queued updates.

A successful delivery prints an identity-only line such as
`Delivered message 100:100:123 (HTTP 202)`. Inspect that message's report with:

```powershell
Invoke-RestMethod "http://127.0.0.1:8765/messages/123/report?telegram_account_id=100&chat_id=100"
```

Optional delivery timing settings are documented in the safe root [`.env.example`](.env.example).
The backend API is unauthenticated, so keep services bound to `127.0.0.1` and use low-sensitivity
test chats only.

## Runtime modes

- `app.demo:app`: backend API plus the static frontend at `/demo/`.
- `app.main:app`: backend API only.
- `TECH4CITY_STORAGE=memory`: fastest disposable storage.
- `TECH4CITY_STORAGE=mongodb`: persistent messages, jobs, and analysis runs.
- `TECH4CITY_ANALYZER=fake`: deterministic software-contract testing.
- `TECH4CITY_ANALYZER=layer1`: local classifier through the same worker contract.

The frontend uses a same-origin WebSocket for login, chat, message, and analysis notifications.
REST remains authoritative, and the frontend falls back to two-second polling while the socket is
unavailable. The WebSocket broker is process-local, so run only one Uvicorn worker.

## Preprocessing and research

Run Confessit preprocessing from the repository root after first-time setup:

```powershell
.\.venv\Scripts\python.exe -m utils.preprocess_confessit --input_file data/nusconfessit.json --output_file data/nus_processed.json
.\.venv\Scripts\python.exe -m utils.preprocess_confessit --input_file data/ntuconfessit.json --output_file data/ntu_processed.json
```

The optional scripts under `utils/` and Layer 2 experiments use a larger scientific/LLM
dependency set:

```powershell
python -m uv sync --locked --dev --extra research
```

Run utility modules with `.\.venv\Scripts\python.exe`. Utilities that call OpenAI require
`OPENAI_API_KEY` in the ignored root `.env`.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
node --check frontend/app.js
```

The first three commands cover the Python application. Run the final command only when Node.js is
installed.

To include the live MongoDB repository test while the Compose service is running:

```powershell
$env:MONGODB_TEST_URI = (Get-Content backend\.env | Select-String '^MONGODB_URI=').Line.Split('=', 2)[1]
.\.venv\Scripts\python.exe -m pytest backend\tests\test_mongo_repository.py -v
Remove-Item Env:MONGODB_TEST_URI
```

## Technical documentation

- [Architecture](ARCHITECTURE.md): system design, boundaries, data flow, and current limitations.
- [Backend reference](backend/README.md): runtime configuration, persistence, API contracts, and
  WebSocket events.
- [TDLib guide](README-TDLIB.md): native build, Telegram credentials, interactive account tests,
  and security.
- [Frontend folder](frontend/README.md): static interface structure and runtime behavior.
