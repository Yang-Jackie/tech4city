# tech4city

Local application for testing Telegram message ingestion and analysis through a FastAPI backend
and a React frontend.

Use the dedicated [application startup guide](README-APP.md) for the current two-process workflow.
`start_demo.ps1` starts the backend, analysis worker, WebSocket notifications, and browser-managed
Telegram support. The `frontend/` React interface runs separately on port 5174 during development.

## Prerequisites

The supported local workflow uses 64-bit Windows and PowerShell.

- Git
- Python 3.11
- PowerShell 5.1 or newer
- Docker Desktop only for the optional MongoDB test
- Node.js only for the optional frontend syntax check

Real Telegram testing also requires the native tools in the
[TDLib guide](README-TDLIB.md#prerequisites).

## First-time setup

Run all commands from the repository root:

```powershell
py -3.11 --version
py -3.11 -m pip install --user "uv>=0.11,<1"
py -3.11 -m uv sync --locked --dev --link-mode=copy
```

This creates `.venv` and installs the local project.

## Test 1: fastest local test

This is the recommended first test. It uses memory storage and a deterministic fake analyzer. It does not require Docker, TDLib, Telegram credentials, a model, or an API key.

Create the backend configuration if necessary. Confirm these values in `backend/.env`:

```dotenv
TECH4CITY_STORAGE=memory
TECH4CITY_ANALYZER=fake
TECH4CITY_WORKER_ENABLED=true
TECH4CITY_WORKER_POLL_SECONDS=0.25
```

### Terminal 1: start the application

```powershell
.\scripts\start_demo.ps1
```

Expected startup:

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8765
```

Open `http://127.0.0.1:8765/`.

### Terminal 2: add sample conversations

```powershell
.\.venv\Scripts\python.exe backend\scripts\seed_demo.py
```

Expected result:

```text
Backend ready: storage=memory analyzer=fake-v1
Seeded 12 sanitized messages across 4 chats.
All analysis jobs completed.
```

Open the URL printed by the command. The sample account ID is `900001`.

Memory storage is disposable: messages and results disappear when Terminal 1 stops.

## Test 2: Layer 1 analysis

Complete Test 1 first. Stop the application with Ctrl+C before installing the ML dependencies.

### Install the ML extra

```powershell
py -3.11 -m uv sync --locked --dev --extra ml --link-mode=copy
```

Confirm that the packages are installed without importing the full ML stack:

```powershell
.\.venv\Scripts\python.exe -c "import importlib.util as u; print({n: bool(u.find_spec(n)) for n in ('peft', 'torch', 'transformers')})"
```

All three values should be `True`.

### Configure Layer 1

Set these values in `backend/.env`:

```dotenv
TECH4CITY_STORAGE=memory
TECH4CITY_ANALYZER=layer1
TECH4CITY_LAYER1_MODEL_DIR=Layer/cyberbully-roblox-pii-lora-synbullying/best_model
TECH4CITY_LAYER1_PIPELINE_VERSION=layer1-roblox-pii-lora-synbullying-v1
```

The tracked files are a PEFT/LoRA adapter for the gated
`Roblox/roblox-pii-classifier` base model. If the base model is not already cached, obtain access
from its owner and add this only to the ignored `backend/.env`:

```dotenv
HF_TOKEN=your_approved_huggingface_token
```

Never commit the token.

### Test the model before starting the application

Use the backend adapter for the smoke test. Do not use `from Layer.Layer1 import Layer1`, because
the `Layer` package currently imports Layer 2 and its separate research dependencies.

```powershell
.\.venv\Scripts\python.exe -c "import asyncio; from pathlib import Path; from dotenv import load_dotenv; load_dotenv('backend/.env'); from app.analyzer import Layer1Analyzer; from app.models import MessageCreate; analyzer=Layer1Analyzer(pipeline_version='smoke-test', model_dir=Path(r'Layer\cyberbully-roblox-pii-lora-synbullying\best_model').resolve()); message=MessageCreate(telegram_account_id=1, chat_id=1, message_id=1, sender_id=1, text='This is a neutral test message.', sent_at='2026-07-28T00:00:00Z'); print(asyncio.run(analyzer(message, [])).model_dump())"
```

The first run may download the base model and initialize CUDA. Continue only after it prints a
result containing `status`, `raw_label`, `normal_score`, and `bully_score`.

### Run the application and seed data

Terminal 1:

```powershell
.\scripts\start_demo.ps1
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe backend\scripts\seed_demo.py
```

Expected health configuration:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

```text
storage  : memory
analyzer : layer1-roblox-pii-lora-synbullying-v1
```

The health endpoint confirms the selected analyzer. The model itself loads lazily when the first
message is analyzed, which is why the direct smoke test is important.

## Test 3: gated Layer 2 placeholder

Complete Test 2 first. The real-user pipeline does not load the current Node2Vec-backed Layer 2
model because Telegram users have no compatible user embedding.

Set these values in `backend/.env`:

```dotenv
TECH4CITY_ANALYZER=layer1-layer2
TECH4CITY_LAYER2_PIPELINE_VERSION=layer2-skipped-real-user-v1
```

Every new message runs through Layer 1. A `not_cyberbully` result stops downstream analysis. A
`need_to_investigate` result reaches Layer 2, which records `status: skipped` and
`skip_reason: real_user_embedding_unavailable` without a score. This is intentional until the ML
owner provides a real-user cold-start contract.

## Test 4: direct Layer 3 analysis

Layer 3 can run without installing the Layer 1 and Layer 2 model runtimes. Install its client:

```powershell
py -3.11 -m uv sync --locked --dev --extra layer3 --link-mode=copy
```

Set the runtime contract and your secret key in the ignored `backend/.env`:

```dotenv
TECH4CITY_STORAGE=memory
TECH4CITY_ANALYZER=layer3
TECH4CITY_LAYER3_MODEL=chatgpt-answer
TECH4CITY_LAYER3_PIPELINE_VERSION=layer3-chatgpt-answer-v1
OPENAI_API_KEY=your_openai_api_key
```

Start the application and use a sanitized message through `POST /messages` or the seed tooling.
Layer 3 receives the stored chronological context plus an explicit `focus_message_id` for the new
message. Its decision, severity, categories, and explanation must describe that focused message;
earlier messages are context only.

For the complete real-user pipeline, install Layer 1 and Layer 3 and change the analyzer mode:

```powershell
py -3.11 -m uv sync --locked --dev --extra ml --extra layer3 --link-mode=copy
```

```dotenv
TECH4CITY_ANALYZER=layer1-layer2-layer3
```

In this mode, Layer 1 gates the pipeline. Layer 2 records a no-score skipped result. Layer 3 runs
only for `need_to_investigate` messages and focuses on the new message. OpenAI Structured Outputs
use `text.format` with the existing strict JSON schema.

## Test 5: connect a real Telegram account

This path uses a TDLib client embedded in `start_demo`. It does not require or start another
bridge process.

### Prepare TDLib

Follow [README-TDLIB.md](README-TDLIB.md) to:

1. Install the native build prerequisites.
2. Build `tdjson.dll`.
3. Obtain `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.

Create the root configuration if necessary:

```powershell
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}
```

Set the credentials in the ignored root `.env`:

```dotenv
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TDJSON_PATH=telegram/.tdlib-build/install/bin/tdjson.dll
TDLIB_DATABASE_ENCRYPTION_KEY=
TDLIB_USE_TEST_DC=false
```

### Connect Telegram from the frontend

1. Run `.\scripts\start_demo.ps1` for the backend.
2. Start `frontend` by following [README-APP.md](README-APP.md#5-start-the-current-frontend).
3. Open `http://127.0.0.1:5174/` and select **Connect Telegram**.
4. Complete the phone, code, and optional two-step-verification prompts.
5. Choose a chat from the Telegram chat list.
6. Open the chat to store its latest 100 text messages as local context.
7. Send a new text message in that Telegram chat to test live analysis.

Login and chat listing do not import messages. Opening a chat imports its recent text history,
stores it without creating analysis jobs, and makes that chat the active source for live TDLib
`updateNewMessage` events. Only new text events in the active chat are queued for analysis.
The frontend receives message and analysis updates through the
application WebSocket. No second process is required.

The active chat selection is process-local and is not written to SQLite or MongoDB. Imported
messages and analysis results follow `TECH4CITY_STORAGE`: the default `memory` mode is disposable,
while the optional `mongodb` mode persists them.

For a privacy-safe Layer 3 smoke test, connect only sanitized conversations and send one new
sanitized text message after opening its chat.

Current limitations: only the latest 100 messages are stored when a chat is opened, only new text
messages are analyzed, and sending, edits, deletes, and media analysis are not implemented.

Each browser login uses an isolated encrypted database under `telegram/.tdlib/web`. Do not run two
application processes against the same database. **Log out** through the frontend when you intend
to revoke and remove that local session.

## Optional integrations

### Test MongoDB persistence

Use MongoDB when messages and analysis results must survive an application restart.

1. Start Docker Desktop.
2. Copy `backend/.env.example` to `backend/.env` if necessary.
3. Uncomment the MongoDB block.
4. Replace both password placeholders with the same URL-safe development password.
5. Keep either `TECH4CITY_ANALYZER=fake` or `TECH4CITY_ANALYZER=layer1`.

Start MongoDB:

```powershell
docker compose -f backend\compose.yaml up -d
docker compose -f backend\compose.yaml ps
```

Then run the application normally:

```powershell
.\scripts\start_demo.ps1
```

The health endpoint should report `"storage": "mongodb"`.

Stop MongoDB without deleting data:

```powershell
docker compose -f backend\compose.yaml stop
```

`docker compose -f backend\compose.yaml down` removes the container but keeps the named volume.
Adding `-v` permanently deletes the local database.

## What each command does

| Command | Type | Purpose |
|---|---|---|
| `py -3.11 -m uv sync ...` | One-time or dependency update | Creates or updates `.venv`; stop the application first. |
| `.\scripts\start_demo.ps1` | Long-running | Starts the backend, worker, WebSocket, and embedded Telegram support. Start the React frontend separately for development. |
| `.\.venv\Scripts\python.exe backend\scripts\seed_demo.py` | One-time | Sends 12 sanitized messages to an already-running backend, waits for analysis, then exits. |
| `.\.venv\Scripts\python.exe -m telegram.cli` | Interactive diagnostic | Tests TDLib login, chats, history, and Saved Messages independently. |
| `docker compose ...` | Long-running service | Starts optional persistent MongoDB storage. |

`seed_demo.py` does not start the application. `start_demo.ps1` does not create sample messages.

## Verify

Stop the application before changing dependencies. The offline verification does not require
MongoDB, TDLib network access, or a model:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
.\.venv\Scripts\ruff.exe check backend
```

Current expected result:

```text
67 passed, 2 skipped
```

The skipped tests are the optional live MongoDB tests.

If Node.js is installed:

```powershell
node --check frontend\app.js
```

To include the live MongoDB repository test while MongoDB is running:

```powershell
$env:MONGODB_TEST_URI = (Get-Content backend\.env | Select-String '^MONGODB_URI=').Line.Split('=', 2)[1]
.\.venv\Scripts\python.exe -m pytest backend\tests\test_mongo_repository.py -v
Remove-Item Env:MONGODB_TEST_URI
```

## Common problems

### `uv sync` reports `Access is denied`

A running Python process is using `.venv`. Stop `start_demo`, tests, and Python shells before
retrying. If necessary, delete only `.venv` and recreate it with the first-time setup command.
Do not delete `.env`, `backend/.env`, `telegram/.tdlib`, `.tdlib-build`, or `Layer/`.

### Layer 1 reports `No module named peft`

The ML extra was not installed:

```powershell
py -3.11 -m uv sync --locked --dev --extra ml --link-mode=copy
```

### Hugging Face returns an authorization error

The adapter references a gated base model. Confirm that the account has access and that
`HF_TOKEN` is set in the ignored `backend/.env`.

### Importing Layer 1 asks for `sentence_transformers`

`from Layer.Layer1 import Layer1` executes `Layer/__init__.py`, which currently imports Layer 2.
Use the backend-adapter smoke test documented above. Layer 2 dependencies are not required for
Layer 1 application testing.

### TDLib reports that `td.binlog` is locked

Only one TDLib client may open a session database. Stop other tech4city application processes and
retry. Concurrent requests within one application share a single restoration task.

### Seeded messages disappear

`TECH4CITY_STORAGE=memory` is intentionally disposable. Use the MongoDB test configuration when
restart persistence is required.

### `seed_demo.py` reports `analysis failed`

The backend accepted the messages, but the configured analyzer failed. For Layer 1, run the direct
smoke test first so dependency, token, download, and model errors are visible outside the worker.

## Research utilities

Other research and training utilities are not required for application testing. Install them
separately:

```powershell
py -3.11 -m uv sync --locked --dev --extra research --link-mode=copy
```

Utilities that call OpenAI require `OPENAI_API_KEY` in the ignored root `.env`.

## Technical documentation

- [Application startup](README-APP.md): current backend, React frontend, Telegram smoke, health,
  shutdown, and troubleshooting workflow.
- [Architecture](ARCHITECTURE.md): system design, boundaries, and current limitations.
- [Backend reference](backend/README.md): configuration, persistence, API contracts, and WebSocket
  events.
- [TDLib guide](README-TDLIB.md): native build, credentials, interactive tests, and security.
- [Frontend folder](frontend/README.md): React structure, development workflow, production build, and runtime behavior.
