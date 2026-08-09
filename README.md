# Detectives

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.139+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![PyTorch](https://img.shields.io/badge/PyTorch-2.7+-EE4C2C?logo=pytorch&logoColor=white)
![Current adapter](https://img.shields.io/badge/Current_adapter-Telegram%2FTDLib-26A5E4?logo=telegram&logoColor=white)

---

## Why?

Cyberbullying rarely fits into one obvious keyword. A harmful message can depend on who said it, what came before it, and whether it forms part of a targeted pattern. At the same time, a rude or
sarcastic message is not automatically cyberbullying.


The current Tech4City prototype uses Telegram through TDLib as its first reference adapter. Future adapters can translate other chat platforms into a shared conversation contract while leaving the core analysis layers intact. Detectives supports human review; it does not claim to replace
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

---

## Quick start

### 1. Install the project

From the repository root:

```powershell
pip install --user "uv>=0.11,<1"
uv sync --locked --dev --link-mode=copy

cd frontend
npm ci
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
.\scripts\start_demo.ps1 # runs at http://localhost:8765 
```

### 4. Start the frontend

In a second terminal:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort # runs at http://localhost:5174
```

---

## Connect Telegram

Follow the complete [TDLib guide](docs/README-TDLIB.md) to build `tdjson.dll` and obtain
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
uv sync --locked --dev --extra ml --extra layer3 --link-mode=copy
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
[application guide](docs/README-APP.md).

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

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for component boundaries, persistence, event flow, and the current unsupported cases.
