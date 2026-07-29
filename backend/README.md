# Backend

FastAPI backend for idempotent message ingestion, queued analysis, conversation reads, and
message reports. It supports process-local memory for offline development and MongoDB for
persistent messages, jobs, and versioned analysis runs. New jobs run automatically through
either the offline `fake-v1` analyzer or the configured local Layer 1 classifier.

See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for the backend component and data-flow design.
Use the root [`README.md`](../README.md) for installation, startup, optional MongoDB and Layer 1
operation, Telegram workflows, and verification.

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

## Message ingestion contract

`POST /messages` is the public equivalent of `processIncomingMessage()` for seed tools and other
approved producers. It accepts normalized new text messages:

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

The HTTP response contract is:

- `202 Accepted`: a new message was stored and queued.
- `200 OK`: an identical replay was already accepted.
- `409 Conflict`: the same account/chat/message identity has different immutable content.
- `422 Unprocessable Entity`: the normalized event is invalid.

The combined application exposes a browser-owned login flow at
`/telegram/login`. It supports phone, code, and Telegram two-step verification,
with one isolated TDLib client per concurrent account. Cookie-protected routes
list recent Telegram chats without importing them. An explicit chat-open request
selects one chat in process memory, imports up to 100 recent messages, and queues
its text messages for analysis. See the root
[Telegram frontend guide](../README.md#connect-telegram-from-the-frontend) for operation and
storage details.

## Live event connection

`GET /ws` upgrades to the single-process WebSocket event channel. Browsers send a `subscribe`
command for either a demo `account_id` or an owned `telegram_session_id`. The backend emits
sequenced `telegram.authorization.changed`, `telegram.logged_out`, `chat.updated`,
`message.created`, and `analysis.updated` events. A bounded connection queue emits
`resync.required` if a browser falls behind. REST snapshots remain authoritative and the frontend
uses its previous two-second polling only while WebSocket is unavailable.

This broker is intentionally local to one Uvicorn process. Do not use multiple workers without
first replacing it with a shared broker such as Redis.

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
- `GET /telegram/login/{session_id}/chats`
- `POST /telegram/login/{session_id}/chats/{chat_id}/open`
- `GET /telegram/login/{session_id}/chats/{chat_id}/messages`
- `GET /telegram/login/{session_id}/messages/{message_id}/report`

The fake analyzer remains explicitly synthetic. Layer 1 integration exposes model output but
does not establish or claim model quality, safety, or accuracy. See the root
[verification guide](../README.md#verify) for offline and live MongoDB checks.
