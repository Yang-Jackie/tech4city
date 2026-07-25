# Backend

FastAPI backend for idempotent message ingestion, queued analysis, conversation reads, and
message reports. It supports process-local memory for offline development and MongoDB for
persistent messages, jobs, and versioned analysis runs. New jobs run automatically through
either the offline `fake-v1` analyzer or the configured local Layer 1 classifier.

See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for the backend component and data-flow design.
Use [`../DEMO.md`](../DEMO.md) as the canonical local startup guide for the frontend,
sanitized seed data, Layer 1, MongoDB, and the Telegram bridge.

## Structure

```text
app/main.py              # FastAPI endpoints and application lifecycle
app/models.py            # Public request, response, job, and analysis schemas
app/ingestion.py         # processIncomingMessage-style application service
app/analyzer.py          # Fake and local Layer 1 analyzer adapters
app/worker.py            # One-job processor and automatic lifecycle runner
app/config.py            # Environment-backed storage/analyzer/worker settings
app/repository.py        # Persistence protocol and in-memory implementation
app/mongo_repository.py  # PyMongo async implementation and indexes
compose.yaml             # Authenticated local MongoDB development service
```

## Optional local MongoDB setup

Docker Desktop must be running. From `backend/`:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and replace both password placeholders with the same random URL-safe development
password. The file is ignored by Git; never commit it.

Start MongoDB and wait for it to become healthy:

```powershell
docker compose up -d
docker compose ps
```

Install the locked backend dependencies and start FastAPI:

```powershell
uv sync --dev
uv run uvicorn app.main:app --reload
```

For the real Layer 1 demo, install the optional ML dependencies and set
`TECH4CITY_ANALYZER=layer1` in `.env`:

```powershell
uv sync --dev --extra ml
uv run uvicorn app.main:app --reload
```

The tracked artifact is a PEFT adapter whose `Roblox/roblox-pii-classifier` base model is
gated. Obtain access from its owner and set `HF_TOKEN` only in the ignored `.env` or process
environment; never commit it. First inference downloads the base model if it is not already
cached.

The application reads `backend/.env` at startup. Verify MongoDB is active:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected storage field:

```json
{"status":"ok","storage":"mongodb","analyzer":"fake-v1"}
```

Open `http://127.0.0.1:8000/docs` to ingest a sanitized test message. Restart only FastAPI,
then call the conversation or report endpoint again; the message and job should remain.

Stop MongoDB without deleting its data:

```powershell
docker compose stop
```

Start it again with `docker compose start`. `docker compose down` removes the container but
keeps the named volume. `docker compose down -v` permanently deletes the local database.

## Runtime configuration

- `TECH4CITY_STORAGE`: `memory` (default) or `mongodb`.
- `MONGODB_URI`: MongoDB connection URI; required for MongoDB storage.
- `MONGODB_DATABASE`: database name; defaults to `tech4city`.
- `MONGO_ROOT_USERNAME` and `MONGO_ROOT_PASSWORD`: local Compose initialization credentials.
- `TECH4CITY_ANALYZER`: `fake` (default) or `layer1`.
- `TECH4CITY_WORKER_ENABLED`: starts automatic processing by default.
- `TECH4CITY_WORKER_POLL_SECONDS`: positive queue poll interval; defaults to `0.25`.
- `TECH4CITY_LAYER1_MODEL_DIR`: approved Layer 1 artifact directory.
- `TECH4CITY_LAYER1_PIPELINE_VERSION`: version stored with every Layer 1 result.
- `HF_TOKEN`: approved Hugging Face read token required by the gated Layer 1 base model.

For Atlas, keep `TECH4CITY_STORAGE=mongodb` and replace `MONGODB_URI` with the Atlas connection
string. Do not commit that string.

MongoDB collections and indexes are initialized at application startup:

- `messages`: unique account/chat/message identity and chronological conversation index.
- `analysis_jobs`: pending-job FIFO index.
- `analysis_runs`: versioned results with a latest-result lookup index.

## Demo flow

```text
POST /messages
  -> validate, deduplicate, persist, create job, wake worker
automatic worker
  -> claim job, invoke configured analyzer, persist versioned result
GET /messages/{message_id}/report
  -> return pending, processing, completed, or failed state
```

`POST /internal/worker/run-once` remains a compatibility/debugging hook. It is unauthenticated
and must not be exposed publicly or called while the automatic worker is enabled.

## Telegram bridge contract

The bridge calls `POST /messages`; this is the cross-process equivalent of
`processIncomingMessage()`. The current milestone accepts normalized new text messages only:

```json
{
  "telegram_account_id": 100,
  "chat_id": 200,
  "message_id": 123,
  "sender_id": 300,
  "text": "Sanitized test message",
  "sent_at": "2026-07-20T10:00:00Z"
}
```

The response contract is:

- `202 Accepted`: a new message was stored and queued.
- `200 OK`: an identical replay was already accepted.
- `409 Conflict`: the same account/chat/message identity has different immutable content.
- `422 Unprocessable Entity`: the normalized event is invalid.

The Telegram bridge requires a non-empty `TECH4CITY_BRIDGE_ALLOWED_CHAT_IDS`, ignores all other
chats before queueing, and implements ordered delivery with in-memory transient retries. Backend
authentication and a durable bridge outbox are not implemented in this demo.

The combined demo additionally exposes a browser-owned login flow at
`/telegram/login`. It supports phone, code, and Telegram two-step verification,
with one isolated TDLib client per concurrent account. Cookie-protected chat
routes expose Saved Messages only. See `../DEMO.md` for operation and storage
details.

## Layer 1 result contract

In `layer1` mode, reports expose the classifier's `status`, `raw_label`, `normal_score`, and
`bully_score` under the versioned `layer1` field. `harmful`, `severity`, `categories`, and
`explanation` remain null until the ML owner supplies an approved mapping specification.


## Endpoints

- `GET /health`
- `POST /messages`
- `POST /internal/worker/run-once`
- `GET /chats?telegram_account_id=...`
- `GET /chats/{chat_id}/messages?telegram_account_id=...`
- `GET /messages/{message_id}/report?telegram_account_id=...&chat_id=...`

## Verify

Offline tests do not require MongoDB:

```powershell
uv run pytest
uv run ruff check .
```

To include the live MongoDB repository test while the Compose service is running:

```powershell
$env:MONGODB_TEST_URI = (Get-Content .env | Select-String '^MONGODB_URI=').Line.Split('=', 2)[1]
uv run pytest tests/test_mongo_repository.py -v
Remove-Item Env:MONGODB_TEST_URI
```

The fake analyzer remains explicitly synthetic. Layer 1 integration exposes model output but
does not establish or claim model quality, safety, or accuracy.
