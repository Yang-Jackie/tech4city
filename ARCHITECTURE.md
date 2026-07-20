# Backend Architecture and Current Workflow

## What We Can Offer Now

The backend currently offers a complete, testable path from a normalized Telegram text event to
a stored analysis result. The TDLib bridge is a separate process owned by the Telegram developer;
the frontend is deferred. The backend boundary between them is ready to use today.

| Capability | Current status |
|---|---|
| Accept a new Telegram text message | Implemented through `POST /messages`. |
| Reject malformed or conflicting events | Implemented with strict validation, idempotency, and HTTP 409/422 responses. |
| Persist messages and analysis state | Implemented in memory or MongoDB; authenticated MongoDB restart persistence was tested. |
| Run analysis after ingestion | Implemented with an automatic in-process worker. |
| Develop and demo without an ML model | Implemented with the deterministic `fake` analyzer. |
| Invoke the repository's existing Layer 1 classifier | Software integration implemented; real inference is blocked until gated model access is configured. |
| Read a conversation and a message's analysis status/result | Implemented through the conversation and report APIs. |
| Serve a frontend chat interface | Not implemented yet; the read APIs are available for later frontend work. |
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
   | TDLib updateNewMessage (ordered update stream)
   v
TDLib bridge [friend-owned]
   |  filter new text messages
   |  normalize Telegram fields
   |  POST /messages and retry transient delivery failures
   v
Backend API [implemented]
   |  validate -> deduplicate -> persist message -> ensure analysis job
   |                                      |
   |  return 202/200 immediately           | wake automatic worker
   |                                      v
   |                              Analysis worker [implemented]
   |                                      |
   |                              claim FIFO persisted job
   |                                      |
   |                         fake analyzer or Layer 1 adapter
   |                                      |
   |                         persist versioned result/failure
   v                                      v
MongoDB [optional, implemented] <---- messages + jobs + analysis runs
   |
   | GET conversation / GET message report
   v
Frontend or API consumer [frontend deferred]
```

Important timing behavior: accepting a message and analyzing it are separate. A successful 202
means the message and its job were accepted, not that analysis has already completed. Consumers
poll the report endpoint to observe `pending`, `processing`, `completed`, or `failed`.

### Ownership at Each Boundary

| Owner | Provides now | Does not currently provide |
|---|---|---|
| TDLib bridge developer | Telegram authorization/client lifecycle and the feasibility client. | A finished live-to-backend connector, durable retry/outbox, edits, deletes, or media forwarding. |
| Backend | HTTP ingestion, validation, deduplication, storage, job execution, analyzer adapter, conversations, and reports. | API authentication, tenant authorization, production recovery/operations, or frontend UI. |
| ML owner | Existing Layer 1 artifact and model-behavior decisions. | An approved mapping from raw Layer 1 scores to harmful/severity/category claims. |
| Frontend developer | Can later consume conversation and report APIs. | Frontend work is intentionally deferred. |

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
| `analyzer.py` | Injectable analysis interface, deterministic fake adapter, and lazy local Layer 1 adapter. |
| `config.py` | Environment-backed selection of storage, analyzer, worker behavior, model artifact, and pipeline version. |

Dependencies point inward: routes and workers depend on protocols and schemas, while MongoDB and
Layer 1 are replaceable adapters. Network access and heavyweight model loading do not occur at
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

The bridge should handle responses as follows:

| Response | Meaning | Bridge action |
|---|---|---|
| `202 Accepted` | New message stored and queued. | Treat delivery as successful. |
| `200 OK` | Identical event was already accepted. | Treat delivery as successful. |
| `409 Conflict` | Same identity was previously stored with different immutable content. | Do not retry blindly; log/investigate normalization. |
| `422 Unprocessable Entity` | Payload does not satisfy the backend schema. | Do not retry unchanged; correct the bridge payload. |
| Network error or `5xx` | Delivery or backend failed transiently. | Retry the exact same payload with bounded backoff. |

This HTTP operation is the cross-process equivalent of `processIncomingMessage()`. The friend
does not import backend Python or call Layer 1 directly. The bridge preserves TDLib update order
and stable Telegram IDs; the backend owns everything after successful HTTP delivery.

The implemented event scope is new text messages only. Edits, deletions, media, secret chats,
authentication, and delivery retry/outbox behavior are not part of the current backend contract.

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

Two adapters exist:

- `fake`: deterministic offline behavior for development and tests.
- `layer1`: lazily loads the existing synchronous classifier, runs inference in a worker thread,
  and stores raw `status`, `raw_label`, `normal_score`, and `bully_score` fields.

Higher-level `harmful`, `severity`, `categories`, and `explanation` values remain null in Layer 1
mode until the ML owner approves an explicit mapping. The pipeline version and model artifact path
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
the full Telegram message identity. These parameters identify data but are not authorization—the
current API is unauthenticated and must not be exposed publicly.

The existing public fields remain available. Layer 1 data is additive under `analysis.layer1`.

## Configuration and Deployment Modes

```text
Storage:   TECH4CITY_STORAGE=memory | mongodb
Analyzer:  TECH4CITY_ANALYZER=fake | layer1
Worker:    TECH4CITY_WORKER_ENABLED=true | false
```

Memory plus fake analysis is the default offline mode. MongoDB provides persistence across backend
restarts. Layer 1 is an optional dependency extra and requires the approved local artifact, its
gated base-model access through `HF_TOKEN`, and an explicit pipeline version.

The entries in `backend/.env.example` document these selectable integration contracts. They do not
contain working secrets and are not all required in every mode. `MONGODB_URI` is required only for
MongoDB mode, and `HF_TOKEN` is required only when the chosen Layer 1 dependency needs gated model
access. A developer creates an ignored `backend/.env` with real local values; none is currently
committed or provisioned as a permanent deployment.

The current deployment is a development modular monolith. It has no API authentication, tenant
authorization, bounded retention, retry policy, processing lease, production secret management,
backup policy, metrics, or CI.

## Verification Status

- Twenty offline tests pass without MongoDB, network access, or heavyweight model loading.
- Two opt-in tests passed against a real authenticated MongoDB instance, including persistence
  through a FastAPI restart.
- The MongoDB instance used for verification was temporary and was removed afterward; MongoDB is
  implemented but is not currently running or permanently configured for this repository.
- Layer 1-shaped ingestion, execution, and persistence are tested through an injected classifier.
- Live inference with the tracked Layer 1 artifact is not verified because its gated base model
  rejected unauthenticated access.
- No live TDLib-to-backend end-to-end run exists yet because the bridge connector belongs to the
  TDLib integration milestone and is not present in the current worktree.

## Repository Layout

```text
backend/
|-- app/
|   |-- main.py
|   |-- models.py
|   |-- ingestion.py
|   |-- repository.py
|   |-- mongo_repository.py
|   |-- worker.py
|   |-- analyzer.py
|   `-- config.py
|-- tests/
|-- compose.yaml
|-- pyproject.toml
|-- uv.lock
`-- README.md
```

## Next Backend Priorities

1. Add authenticated account/tenant scoping to every API operation.
2. Add processing leases, crash recovery, bounded retries, and dead-letter visibility.
3. Define retention/deletion and transactional consistency policies.
4. Add structured operational logging, metrics, health/readiness separation, and CI.
5. Apply an ML-owner-approved mapping only if higher-level findings are required.

## Explicitly Unsupported Today

- Telegram message edits, deletions, media, secret chats, and historical-backfill semantics.
- Bridge authentication, durable delivery outbox, and backend-managed bridge retries.
- User/chat management, API login, per-user access control, and multi-tenant isolation.
- Automatic recovery of jobs stranded in `processing`, bounded retries, and dead-letter handling.
- Transactional message/job and result/completion writes or reconciliation after partial failure.
- Retention/deletion enforcement, backups, production secrets, operational metrics, and CI.
- A frontend, push notifications, streaming status updates, or WebSocket delivery.
- Verified model-quality, safety, accuracy, threshold, or higher-level harmfulness claims.
