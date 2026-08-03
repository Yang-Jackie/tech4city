# Detectives backend

FastAPI backend for idempotent message ingestion, queued analysis, conversation reads, and
message reports. It supports process-local memory for offline development and MongoDB for
persistent messages, jobs, and versioned analysis runs. New jobs run automatically through
the offline `fake-v1` analyzer, Layer 1, Layer 3, or an additive multi-layer pipeline.

See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for the backend component and data-flow design.
Use the root [`README.md`](../README.md) for installation, startup, optional MongoDB and local
model operation, Telegram workflows, and verification.

## Structure

```text
app/main.py              # FastAPI endpoints and application lifecycle
app/models.py            # Public request, response, job, and analysis schemas
app/ingestion.py         # processIncomingMessage-style application service
app/analyzer.py          # Fake and injectable Layer 1/2/3 adapters
app/worker.py            # One-job processor and automatic lifecycle runner
app/config.py            # Environment-backed storage/analyzer/worker settings
app/repository.py        # Persistence protocol and in-memory implementation
app/mongo_repository.py  # PyMongo async implementation and indexes
compose.yaml             # Authenticated local MongoDB development service
```

## Runtime configuration

- `DETECTIVES_STORAGE`: `memory` (default) or `mongodb`.
- `MONGODB_URI`: MongoDB connection URI; required for MongoDB storage.
- `MONGODB_DATABASE`: database name; defaults to `detectives`.
- `MONGO_ROOT_USERNAME` and `MONGO_ROOT_PASSWORD`: local Compose initialization credentials.
- `DETECTIVES_ANALYZER`: `fake` (default), `layer1`, `layer1-layer2`, `layer3`, or
  `layer1-layer2-layer3`.
- `DETECTIVES_WORKER_ENABLED`: starts automatic processing by default.
- `DETECTIVES_WORKER_POLL_SECONDS`: positive queue poll interval; defaults to `0.25`.
- `DETECTIVES_LAYER1_MODEL_DIR`: approved Layer 1 artifact directory.
- `DETECTIVES_LAYER1_PIPELINE_VERSION`: version stored with every Layer 1 result.
- `DETECTIVES_LAYER2_CLASSIFIER_HEAD_PATH`: reserved Layer 2 research artifact; the real-user
  pipeline does not load it while cold-start behavior is unspecified.
- `DETECTIVES_LAYER2_TEXT_EMBEDDING_MODEL`: reserved Layer 2 research encoder identifier.
- `DETECTIVES_LAYER2_PIPELINE_VERSION`: version for the explicit skipped Layer 2 stage.
- `DETECTIVES_LAYER3_MODEL`: existing Layer 3 model identifier; defaults to `chatgpt-answer`.
- `DETECTIVES_LAYER3_PIPELINE_VERSION`: version stored with Layer 3 results.
- `OPENAI_API_KEY`: required when Layer 3 runs. Backend startup loads `backend/.env` first,
  then the repository-root `.env` as a fallback; existing process variables always win.
- `HF_TOKEN`: approved Hugging Face read token required by the gated Layer 1 base model.

For Atlas, keep `DETECTIVES_STORAGE=mongodb` and replace `MONGODB_URI` with the Atlas connection
string. Do not commit that string.

The former `TECH4CITY_*` names remain accepted as lower-priority compatibility aliases. New
configuration should use `DETECTIVES_*`. A legacy `TECH4CITY_STORAGE=mongodb` configuration
without `MONGODB_DATABASE` continues to use the former database name so existing local data is
not hidden during the rename.

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
selects one chat in process memory and stores up to 100 recent text messages as
context without analysis jobs. Only new text events in that chat are queued. See the root
[Telegram frontend guide](../README.md#connect-telegram) for operation and
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

## Local model result contract

In `layer1` mode, reports expose the classifier's `status`, `raw_label`, `normal_score`, and
`bully_score` under the versioned `layer1` field. `harmful`, `severity`, `categories`, and
`explanation` remain null until the ML owner supplies an approved mapping specification.

In `layer1-layer2` mode, Layer 1's existing `status` is the gate. `not_cyberbully` stops the
pipeline. `need_to_investigate` reaches an explicit Layer 2 placeholder that returns no score and
records `skip_reason: real_user_embedding_unavailable`. The current Node2Vec-backed weights are
not invoked for real Telegram users.

In `layer3` mode, the adapter sends prior stored messages, the current message, and an explicit
`focus_message_id`. Layer 3 uses prior messages only as context and evaluates the focused new
message. Reports expose its validated output under `layer3`; confidence remains under
`layer3.analysis.confidence` and is not relabeled as bully probability. In
`layer1-layer2-layer3` mode, Layer 3 runs only after Layer 1 returns `need_to_investigate`.


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
- `GET /telegram/login/{session_id}/chats/{chat_id}/reports`
- `GET /telegram/login/{session_id}/chats/{chat_id}/messages/{message_id}/report`
- `GET /telegram/login/{session_id}/messages/{message_id}/report`

The fake analyzer remains explicitly synthetic. Local model integration exposes raw output but
does not establish or claim model quality, safety, or accuracy. See the root
[testing guide](../README.md#testing) for offline and live MongoDB checks.

Analyzer failures remain `analysis failed` in the public job contract. The backend log records
the job ID, real exception type, sanitized exception message, and traceback; message text and
credential-like values are redacted.
