# Detectives Architecture and Current Workflow

## What We Can Offer Now

The backend accepts normalized Telegram messages, stores analysis results, and serves a multi-chat
WebSocket-enabled frontend. Browser-owned TDLib clients list recent Telegram chats without
importing them. When the user opens a chat, the client imports its latest history and streams new
text messages from that selected chat into the application service.

| Capability | Current status |
|---|---|
| Accept a new Telegram text message | Implemented through browser-managed TDLib and `POST /messages`. |
| Reject malformed or conflicting events | Implemented with strict validation, idempotency, and HTTP 409/422 responses. |
| Persist messages and analysis state | Implemented in memory or MongoDB; authenticated MongoDB restart persistence was tested. |
| Run analysis after ingestion | Implemented with an automatic in-process worker. |
| Develop and demo without an ML model | Implemented with the deterministic `fake` analyzer. |
| Invoke model-backed layers | Layer 1 gates downstream work; Layer 2 is an explicit no-score real-user placeholder; Layer 3 evaluates the referred new message with earlier context. |
| Discover stored chats and read conversation/message analysis | Implemented through chat-summary, conversation, and report APIs. |
| List and select a Telegram chat | Implemented through browser-owned TDLib routes; selection is process-local and not persisted. |
| Serve a frontend chat interface | Implemented as a responsive React chat-review application; a production build is served at `/demo/` by `app.demo:app`. |
| Operate as a secure production service | Not yet; authentication, recovery, retention, observability, and deployment hardening remain. |

## Scope

The backend is a modular FastAPI application that accepts normalized text messages, stores
idempotent message and job state, runs asynchronous analysis, persists versioned results, and
serves conversation and report reads. This document describes the whole team-facing workflow but
only assigns implementation ownership to the backend where the request crosses its HTTP boundary.
Telegram/TDLib lifecycle, user interfaces, and ML-quality decisions remain separately owned.

## End-to-End Team Workflow

```text
Telegram
   |
   | getChats -> user opens one chat -> getChatHistory/updateNewMessage
   v
TelegramSessionManager [embedded in FastAPI]
   |  verify browser ownership and filter the session-selected chat
   |  normalize Telegram fields
   |  call IncomingMessageService directly
   v
Backend application service [implemented]
   |  validate -> deduplicate -> persist message -> ensure analysis job
   |                                      |
   |  return 202/200 immediately           | wake automatic worker
   |                                      v
   |                              Analysis worker [implemented]
   |                                      |
   |                              claim FIFO persisted job
   |                                      |
   |                   fake or configurable Layer 1/2/3 pipeline
   |                                      |
   |                         persist versioned result/failure
   v                                      v
MongoDB [optional, implemented] <---- messages + jobs + analysis runs
   |
   | GET conversation / GET message report
   v
Demo frontend or API consumer [implemented]
```

Important timing behavior: accepting a message and analyzing it are separate. A successful 202
means the message and its job were accepted, not that analysis has already completed. Consumers
poll the report endpoint to observe `pending`, `processing`, `completed`, or `failed`.

### Ownership at Each Boundary

| Owner | Provides now | Does not currently provide |
|---|---|---|
| Telegram integration developer | Browser-owned TDLib authorization, session lifecycle, session-only chat selection, and real-time new-text ingestion. | Sending messages, edits, deletes, or media support. |
| Backend | HTTP ingestion, validation, deduplication, storage, job execution, analyzer adapter, conversations, and reports. | API authentication, tenant authorization, production recovery/operations, or frontend UI. |
| ML owner | Existing Layer 1 artifact and model-behavior decisions. | An approved mapping from raw Layer 1 scores to harmful/severity/category claims. |
| Frontend | Lists Telegram chat titles, explicitly opens one chat for analysis, receives WebSocket updates with REST snapshot recovery, distinguishes sent and received messages, and exposes approved analysis fields in a dismissible drawer. | Production user identity or an ML-approved detailed explanation. |

## Runtime Shape

```text
External message producer
          |
          | POST /messages
          v
+----------------------- FastAPI application -----------------------+
|                                                                   |
|  API routes -> IncomingMessageService -> BackendRepository        |
|                        |                    |                      |
|                        | wake               | messages/jobs/runs   |
|                        v                    v                      |
|               AnalysisWorkerRunner       MongoDB                  |
|                        |                    ^                      |
|                        v                    |                      |
|                 AnalysisWorker ------------+                      |
|                        |                                           |
|                        v                                           |
|              fake-v1 or Layer1Analyzer                            |
|                                                                   |
|  Read routes -----------------------> BackendRepository            |
+-------------------------------------------------------------------+
```

The API and automatic worker currently run in one Python process. The repository contract keeps
storage replaceable and allows tests to run entirely in memory.

## Component Boundaries

| Component | Responsibility |
|---|---|
| `main.py` | Application lifecycle, dependency construction, HTTP routing, and response status mapping. |
| `models.py` | Strict versioned request, job, analysis, health, and report schemas. |
| `ingestion.py` | Application-level incoming-message orchestration independent of HTTP and TDLib. |
| `repository.py` | Storage protocol, message identity helpers, and concurrency-safe in-memory implementation. |
| `mongo_repository.py` | Async MongoDB persistence, indexes, atomic job claims, and document/schema mapping. |
| `worker.py` | FIFO job execution plus the application-lifecycle runner that wakes and polls automatically. |
| `analyzer.py` | Injectable analysis interface plus lazy Layer 1, explicit Layer 2 skip, and new-message-focused Layer 3 adapters. |
| `config.py` | Environment-backed selection of storage, analyzer, worker behavior, model artifact, and pipeline version. |

Dependencies point inward: routes and workers depend on protocols and schemas, while MongoDB and
local model layers are replaceable adapters. Network access and heavyweight model loading do not occur at
module import time.

## Ingestion Contract

`POST /messages` accepts one normalized new text message:

```text
telegram_account_id + chat_id + message_id  -> immutable message identity
sender_id + text + sent_at                   -> normalized message content
```

Example request:

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

Processing is deliberately non-blocking:

1. Pydantic validates the normalized message and rejects extra or malformed fields.
2. `IncomingMessageService` stores the message through `BackendRepository`.
3. The repository treats an identical replay as a duplicate and conflicting immutable content as
   HTTP 409.
4. The service ensures exactly one analysis-job identity and signals the worker when it is pending.
5. The API returns HTTP 202 for a new message or HTTP 200 for an identical replay; it does not wait
   for analysis.

External HTTP producers should handle responses as follows:

| Response | Meaning | Producer action |
|---|---|---|
| `202 Accepted` | New message stored and queued. | Treat delivery as successful. |
| `200 OK` | Identical event was already accepted. | Treat delivery as successful. |
| `409 Conflict` | Same identity was previously stored with different immutable content. | Do not retry blindly; log/investigate normalization. |
| `422 Unprocessable Entity` | Payload does not satisfy the backend schema. | Do not retry unchanged; correct the payload. |
| Network error or `5xx` | Delivery or backend failed transiently. | Retry the exact same payload with bounded backoff. |

This HTTP operation is the cross-process equivalent of `processIncomingMessage()`. The
browser-managed Telegram session manager runs inside the backend and calls that application
service directly, preserving stable Telegram identities without an HTTP loopback.

The implemented Telegram scope is the latest 100 messages from one explicitly opened chat plus
new text messages received while it remains selected. Listing chats alone imports nothing, and
the selected chat ID is not persisted. Edits, deletions, media, secret chats, deeper historical
backfill, and sending messages are not yet supported.

## Analysis Pipeline

```text
pending -> processing -> completed
                     `-> failed
```

`AnalysisWorkerRunner` starts with the FastAPI lifespan, polls for persisted work, and is also
woken immediately after ingestion. `AnalysisWorker.run_once()` atomically claims one FIFO job,
loads the target message and earlier chronological context, invokes the configured analyzer, and
stores a versioned result or a safe generic failure.

The analyzer interface is asynchronous and injectable:

```text
(message, earlier_context) -> AnalysisResult
```

Five runtime modes exist:

- `fake`: deterministic offline behavior for development and tests.
- `layer1`: lazily loads the existing synchronous classifier, runs inference in a worker thread,
  and stores raw `status`, `raw_label`, `normal_score`, and `bully_score` fields.
- `layer1-layer2`: runs Layer 1 as a gate and records an explicit no-score Layer 2 skip because
  no real-user embedding contract exists yet.
- `layer3`: sends stored chronological context, the current message, and its focus message ID to
  the OpenAI-backed Layer 3 contract without requiring local classifier runtimes.
- `layer1-layer2-layer3`: stops after a clear Layer 1 result; otherwise records the Layer 2 skip
  and runs Layer 3 for the focused new message.

Higher-level `harmful`, `severity`, `categories`, and `explanation` values remain null in local
model modes until an explicit mapping is approved. Pipeline versions and model artifact paths
are configuration contracts rather than hardcoded runtime assumptions.

Layer 1 is therefore not test-only. The fake analyzer is the offline/test option; Layer 1 is the
real local-classifier option. Its adapter is implemented and covered with an injected test double,
but a live model smoke test cannot complete until `HF_TOKEN` has access to the gated
`Roblox/roblox-pii-classifier` base model.

## Persistence Model

MongoDB mode uses three collections:

| Collection | Purpose | Important invariant/index |
|---|---|---|
| `messages` | Immutable normalized messages plus backend receipt time. | Unique `(telegram_account_id, chat_id, message_id)` and chronological chat lookup. |
| `analysis_jobs` | Current durable scheduling state and attempt count. | One job per message and FIFO pending-job claim. |
| `analysis_runs` | Versioned analyzer outputs by attempt. | Latest result lookup per message. |

`MongoRepository.claim_next_job()` performs an atomic pending-to-processing transition, allowing
multiple backend processes to compete safely for MongoDB jobs. The in-memory repository provides
the same protocol with an `asyncio.Lock`, but all state disappears on process restart.

Message insertion and job creation are currently separate writes. Likewise, result insertion and
job completion are not a multi-document transaction. A crash may therefore leave incomplete or
`processing` state; lease recovery and reconciliation remain reliability work.

## Read API

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/health` | Pings active storage and reports storage/analyzer identity. |
| `GET` | `/chats/{chat_id}/messages` | Returns one account/chat conversation chronologically. |
| `GET` | `/messages/{message_id}/report` | Returns the message, current job state, and latest analysis result. |
| `POST` | `/internal/worker/run-once` | Compatibility/debug hook; use only with the automatic worker disabled. |

The conversation endpoint requires `telegram_account_id` as a query parameter. The report endpoint
requires both `telegram_account_id` and `chat_id`; together with the path `message_id`, these form
the full Telegram message identity. These parameters identify data but are not authorizationâ€”the
current API is unauthenticated and must not be exposed publicly.

The existing public fields remain available. Model data is additive under `analysis.layer1`,
`analysis.layer2`, and `analysis.layer3`. Layer 3's already-defined boolean, severity, categories,
and explanation also populate the corresponding top-level analysis fields. Its confidence is not
relabeled as bully probability.

## Runtime Modes

Storage, analysis, and worker implementations are selectable adapters. Memory plus fake analysis
is the default offline shape; MongoDB provides restart persistence; local models replace the analyzer
through the same worker contract. See the [backend reference](backend/README.md#runtime-configuration)
for the exact configuration surface and the root [operational guide](README.md#optional-mongodb-persistence)
for setup.

The current deployment is a development modular monolith. It has no API authentication, tenant
authorization, bounded retention, retry policy, processing lease, production secret management,
backup policy, metrics, or CI.

## Next Backend Priorities

1. Add authenticated account/tenant scoping to every API operation.
2. Add processing leases, crash recovery, bounded retries, and dead-letter visibility.
3. Define retention/deletion, selected-chat persistence, and transactional consistency policies.
4. Add structured operational logging, metrics, health/readiness separation, and CI.
5. Apply an ML-owner-approved mapping only if higher-level findings are required.

## Explicitly Unsupported Today

- Telegram message edits, deletions, media, secret chats, and backfill beyond the latest 100
  messages.
- Persisted Telegram chat selection and sending messages from the application.
- Remote-user application login, tenant management, and multi-tenant isolation. Local Telegram
  sessions are scoped by an HttpOnly browser-ownership cookie.
- Automatic recovery of jobs stranded in `processing`, bounded retries, and dead-letter handling.
- Transactional message/job and result/completion writes or reconciliation after partial failure.
- Retention/deletion enforcement, backups, production secrets, operational metrics, and CI.
- Shared multi-worker WebSocket delivery, durable event replay, and push notifications. The
  current WebSocket broker is single-process and reconnects through REST snapshot recovery.
- Verified model-quality, safety, accuracy, threshold, or higher-level harmfulness claims.
