<div align="center">

# Detectives

An adaptable cyberbullying-analysis brain for online conversations.

Detectives turns chat context into review signals, focused explanations, and actionable
insight.

[How it works](#how-it-works) · [Features](#features) · [Quick start](#quick-start) · [Full pipeline](#run-the-full-analysis-pipeline) · [Architecture](#architecture) · [Privacy](#privacy-and-safety)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.139+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![PyTorch](https://img.shields.io/badge/PyTorch-2.7+-EE4C2C?logo=pytorch&logoColor=white)
![Current adapter](https://img.shields.io/badge/Current_adapter-Telegram%2FTDLib-26A5E4?logo=telegram&logoColor=white)

**Built as a submission for the Tech4City hackathon**

</div>

---

## Why Detectives

Cyberbullying rarely fits into one obvious keyword. A harmful message can depend on who said it,
what came before it, and whether it forms part of a targeted pattern. At the same time, a rude or
sarcastic message is not automatically cyberbullying.

Detectives is the analysis brain behind that workflow, not a Telegram-specific product. It is
designed to receive normalized messages through platform adapters, analyze them through explicit
software contracts, and return versioned results that a connected product can store, display, or
act on.

The current Tech4City prototype uses Telegram through TDLib as its first reference adapter. Future
adapters can translate other chat platforms into a shared conversation contract while leaving the
core analysis layers intact. Detectives supports human review; it does not claim to replace
safeguarding judgment.

---

## How it works

```text
Chat platform
(Telegram through TDLib today)
            ↓
Platform adapter
            ↓
Normalized conversation contract
            ↓
Detectives analysis brain
            ↓
Layer 1 gate → Layer 2 contract → focused Layer 3 review
            ↓
Versioned result API
            ↓
Review interface or another consuming product
```

| Stage | What happens |
|---|---|
| **Adapt** | Each platform adapter converts provider-specific identities, chats, and events into the conversation contract consumed by Detectives. |
| **Collect** | The current Telegram adapter lists recent chats and imports up to 100 text messages from the selected chat as context. |
| **Observe** | New messages supplied by the active adapter enter the analysis queue. |
| **Analyze** | Layer 1 gates further investigation; the current real-user Layer 2 contract records an explicit no-score skip; Layer 3 evaluates the new message with earlier messages as context. |
| **Persist** | Jobs and versioned results use either disposable memory storage or MongoDB. |
| **Review** | The frontend shows completed safe and concerning results without exposing internal pipeline stages. |

Model behavior—including prompts, thresholds, label semantics, and quality acceptance—remains a
versioned ML contract. The application code validates, stores, and displays those outputs without
silently redefining them.

---

## Features

| Area | Capability |
|---|---|
| **Analysis brain** | Consumes normalized conversations and returns versioned, platform-independent analysis results. |
| **Adapter boundary** | Keeps platform authorization, identity, and event formats outside the core analysis pipeline. |
| **Current Telegram adapter** | Browser-managed phone, code, and two-step-verification login using TDLib. |
| **Read-only reference workflow** | Lists chats and reads text messages without sending, editing, or deleting Telegram content. |
| **Context-aware review** | Keeps earlier chronological messages as context while focusing the decision on the new message. |
| **Layered analysis** | Injectable fake, local Hugging Face Layer 1, gated Layer 1/2, direct Layer 3, and combined Layer 1/2/3 modes. |
| **Asynchronous processing** | Idempotent ingestion, queued jobs, an automatic worker, and explicit pending, processing, completed, and failed states. |
| **Live updates** | REST snapshots plus single-process WebSocket events for adapter, message, and analysis changes. |
| **Reviewer interface** | Responsive React conversation list, message states, flagged-message filtering, and a detailed analysis sheet. |
| **Persistence options** | Fast offline memory mode or MongoDB with message identity and analysis lookup indexes. |
| **Offline verification** | Injectable model boundaries and sanitized fixtures keep the core test suite independent of Telegram, MongoDB, and model downloads. |

### Current scope

- Telegram is the only implemented platform adapter today; support for other chat platforms is the intended evolution, not a current capability.
- The analysis layers and versioned result boundary are isolated from TDLib. Each future adapter must supply its own authorization, normalization, identity, and event-delivery behavior.
- The current backend message identity still uses Telegram-named fields and must be generalized as part of adding the next platform adapter.
- In the current Telegram adapter, opening a chat stores its latest 100 text messages as context and only new text messages in the selected chat are analyzed.
- Media, edits, deletions, secret chats, and outbound actions are not implemented in the current adapter.
- Layer 2 is deliberately skipped for real users until the ML owner approves a cold-start and feature contract.
- The backend is a local hackathon application and must not be exposed publicly without authentication, tenant isolation, retention controls, and production deployment hardening.

---

## Quick start

The supported full application workflow uses 64-bit Windows and PowerShell. The offline backend
test requires Python 3.11; the interface additionally requires Node.js 20.19+ or 22.12+.

### 1. Install the project

From the repository root:

```powershell
py -3.11 -m pip install --user "uv>=0.11,<1"
py -3.11 -m uv sync --locked --dev --link-mode=copy

Push-Location frontend
npm ci
Pop-Location
```

### 2. Configure the offline analyzer

Create the ignored backend configuration:

```powershell
if (-not (Test-Path backend\.env)) {
    Copy-Item backend\.env.example backend\.env
}
```

Use the deterministic offline mode in `backend/.env`:

```dotenv
DETECTIVES_STORAGE=memory
DETECTIVES_ANALYZER=fake
DETECTIVES_WORKER_ENABLED=true
DETECTIVES_WORKER_POLL_SECONDS=0.25
```

### 3. Start the backend

```powershell
.\scripts\start_demo.ps1
```

The API runs at <http://127.0.0.1:8765>. OpenAPI documentation is available at
<http://127.0.0.1:8765/docs>.

### 4. Start the frontend

In a second terminal:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Open <http://127.0.0.1:5174>. The first-use screen explains how to connect Telegram. Telegram
login itself requires the native TDLib setup and credentials described below.

---

## Connect Telegram

Follow the complete [TDLib guide](README-TDLIB.md) to build `tdjson.dll` and obtain
`TELEGRAM_API_ID` and `TELEGRAM_API_HASH`. Then copy the root example:

```powershell
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}
```

Set the ignored root `.env`:

```dotenv
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TDJSON_PATH=telegram/.tdlib-build/install/bin/tdjson.dll
TDLIB_DATABASE_ENCRYPTION_KEY=
TDLIB_USE_TEST_DC=false
```

Start both processes, select **Connect Telegram**, complete Telegram authorization, and choose a
chat. Detectives imports recent text as context and queues only new text messages received after
that chat is opened.

Browser-managed TDLib databases are isolated under the ignored `telegram/.tdlib/web/` directory.
Use the frontend logout action when you intend to revoke and remove a local session.

---

## Run the full analysis pipeline

Install the local classifier and Layer 3 dependencies:

```powershell
py -3.11 -m uv sync --locked --dev --extra ml --extra layer3 --link-mode=copy
```

Configure the approved integration contracts in `backend/.env`:

```dotenv
DETECTIVES_STORAGE=memory
DETECTIVES_ANALYZER=layer1-layer2-layer3
DETECTIVES_WORKER_ENABLED=true
DETECTIVES_WORKER_POLL_SECONDS=0.25

DETECTIVES_LAYER1_MODEL_DIR=Layer/cyberbully-roblox-pii-lora-synbullying/best_model
DETECTIVES_LAYER1_PIPELINE_VERSION=layer1-roblox-pii-lora-synbullying-v1
DETECTIVES_LAYER2_PIPELINE_VERSION=layer2-skipped-real-user-v1
DETECTIVES_LAYER3_MODEL=chatgpt-answer
DETECTIVES_LAYER3_PIPELINE_VERSION=layer3-chatgpt-answer-v1

HF_TOKEN=your_approved_huggingface_token
OPENAI_API_KEY=your_openai_api_key
```

The tracked Layer 1 adapter references a gated Hugging Face base model. Obtain access from its
owner before using `HF_TOKEN`. Never commit either token. The first Layer 1 request loads the model
lazily and can take substantially longer than later requests.

The former `TECH4CITY_*` environment variables remain lower-priority compatibility aliases for
existing local setups. New configuration should use `DETECTIVES_*`.

For focused setup, runtime, shutdown, and troubleshooting instructions, use the
[application guide](README-APP.md).

---

## Optional MongoDB persistence

Memory mode loses messages, jobs, and results when the backend stops. To use the authenticated
local MongoDB service:

1. Copy `backend/.env.example` to `backend/.env`.
2. Uncomment the MongoDB block and replace both password placeholders with the same URL-safe local password.
3. Set `DETECTIVES_STORAGE=mongodb`.
4. Start Docker Desktop and run:

```powershell
docker compose -f backend\compose.yaml up -d
.\scripts\start_demo.ps1
```

`docker compose -f backend\compose.yaml down` removes the container but retains the named volume.
Adding `-v` permanently deletes that local database.

---

## Architecture

Detectives keeps model behavior behind an injectable analyzer contract and storage behind a
repository protocol. Its target platform boundary is an adapter that supplies normalized
conversation events to the same analysis brain.

```text
Target adapter shape

Platform adapters → normalized messages → queue → Detectives analysis brain
                                                    ↓
                                      versioned findings and reports
                                                    ↓
                                        any authorized consumer
```

```text
Detectives/
├── Layer/                 # Public Layer API and ML adapters
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI routes and lifecycle
│   │   ├── ingestion.py   # Idempotent message application service
│   │   ├── analyzer.py    # Injectable Layer 1/2/3 integration
│   │   ├── worker.py      # Queue processing and lifecycle runner
│   │   ├── repository.py  # Storage protocol and memory implementation
│   │   └── telegram_login.py
│   └── tests/
├── frontend/              # React, TypeScript, Vite, and Tailwind UI
├── telegram/              # Current TDLib platform adapter
├── utils/                 # Research and data-preparation utilities
└── data/                  # Existing research artifacts and derived datasets
```

The public `Layer` methods and returned fields remain backward compatible. Application adapters
load heavyweight model dependencies lazily, so module import and offline tests do not require a
network connection or model initialization.

See [ARCHITECTURE.md](ARCHITECTURE.md) for component boundaries, persistence, event flow, and the
current unsupported cases.

---

## API overview

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Report storage and analyzer readiness. |
| `POST` | `/messages` | Validate, deduplicate, store, and queue a normalized text message. |
| `GET` | `/chats` | List stored chats for a connected account. |
| `GET` | `/chats/{chat_id}/messages` | Read a stored conversation. |
| `GET` | `/messages/{message_id}/report` | Read the latest versioned result and job state. |
| `POST` | `/telegram/login` | Start an isolated browser-owned Telegram login. |
| `GET` | `/telegram/login/{session_id}/chats` | List chats owned by the browser session. |
| `POST` | `/telegram/login/{session_id}/chats/{chat_id}/open` | Select a chat and import recent text as context. |
| `GET` | `/ws` | Upgrade to the local WebSocket event channel. |

The internal worker hook exists only for compatibility and debugging; it is unauthenticated and
must not be exposed publicly.

---

## Testing

The default verification path is offline and uses sanitized fixtures:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
.\.venv\Scripts\ruff.exe check backend

Push-Location frontend
npm run typecheck
npm run lint
npm run build
Pop-Location

git diff --check
```

Optional live MongoDB tests require `MONGODB_TEST_URI`. Real Telegram and model-backed smoke tests
require their respective credentials and approved artifacts; they are not evidence of model
quality or safety.

---

## Privacy and safety

The Detectives analysis brain is platform-independent; data handling ultimately depends on the
adapter and consuming product around it. The current Telegram adapter requests read-only access
and does not send, edit, or delete Telegram messages. The prototype stores message text locally in
memory or in the configured MongoDB database. Browser-managed Telegram session databases and
credentials remain in ignored local paths and environment files.

When Layer 3 is enabled, the focused message and stored conversation context are sent to the
configured OpenAI model. Connect only accounts and conversations you are authorized to process,
and use sanitized content for development and demonstrations.

Do not commit API keys, Telegram credentials, TDLib session data, raw private conversations, or
personally identifying fixtures. Detectives surfaces model output for review and does not present
unverified accuracy, safety, or efficacy claims.

---

## Documentation

- [Application guide](README-APP.md) — complete local startup, verification, shutdown, and troubleshooting.
- [Architecture](ARCHITECTURE.md) — backend boundaries, runtime flow, storage, and limitations.
- [Backend reference](backend/README.md) — environment, persistence, endpoints, and result contracts.
- [TDLib guide](README-TDLIB.md) — native build, Telegram credentials, diagnostics, and security.
- [Frontend reference](frontend/README.md) — React development, production build, and frontend contracts.

---

<div align="center">

**Detectives · Tech4City hackathon submission**

</div>
