# Run Detectives

This guide starts the current application locally with two processes:

1. The FastAPI backend, analysis worker, WebSocket events, and browser-managed TDLib client on
   `http://127.0.0.1:8765`.
2. The React/Vite frontend from `frontend/` on `http://127.0.0.1:5174`.

During development, port 5174 preserves the established browser-managed Telegram origin. After
`npm run build`, the same React frontend is available from the backend at
`http://127.0.0.1:8765/demo/`.

## Prerequisites

The supported local workflow uses 64-bit Windows and PowerShell.

- Python 3.11.
- `uv` 0.11 or newer.
- Node.js `20.19+` or `22.12+` (Node.js 24 is also supported by the installed Vite version).
- npm.
- The TDLib native build and Telegram application credentials from
  [README-TDLIB.md](README-TDLIB.md) for real Telegram testing.
- Approved access to the Layer 1 base model and an OpenAI API key for the complete pipeline.

Run the application from a normal PowerShell terminal. Restricted automation sandboxes may block
Vite's Windows child-process check or Layer 3 network access even though local health checks pass.

## 1. Install dependencies

From the repository root:

```powershell
py -3.11 -m pip install --user "uv>=0.11,<1"
py -3.11 -m uv sync --locked --dev --extra ml --extra layer3 --link-mode=copy
```

Install the locked frontend dependencies:

```powershell
Push-Location frontend
npm ci
Pop-Location
```

The Python command creates the shared `.venv`. Stop running backend and test processes before
changing this environment.

## 2. Configure the backend

Create the ignored backend configuration if it does not exist:

```powershell
if (-not (Test-Path backend\.env)) {
    Copy-Item backend\.env.example backend\.env
}
```

For the currently approved real-user flow, confirm these settings in `backend/.env`:

```dotenv
DETECTIVES_STORAGE=memory
DETECTIVES_ANALYZER=layer1-layer2-layer3
DETECTIVES_WORKER_ENABLED=true
DETECTIVES_WORKER_POLL_SECONDS=0.25

DETECTIVES_LAYER1_MODEL_DIR=Layer/cyberbully-roblox-pii-lora-synbullying/best_model
DETECTIVES_LAYER1_PIPELINE_VERSION=layer1-roblox-pii-lora-synbullying-v1

DETECTIVES_LAYER2_PIPELINE_VERSION=layer2-skipped-real-user-v1

DETECTIVES_LAYER3_MODEL=gpt-4o-mini
DETECTIVES_LAYER3_PIPELINE_VERSION=layer3-gpt-4o-mini-focused-v1

HF_TOKEN=your_approved_huggingface_token
OPENAI_API_KEY=your_openai_api_key
```

Do not commit either token. If the ML owner approves a different model or pipeline version, use
that approved contract instead of changing it ad hoc.

The configured real-user pipeline behaves as follows:

- Layer 1 analyzes every new selected-chat text message.
- `not_cyberbully` stops the pipeline.
- `need_to_investigate` continues to Layer 2.
- Layer 2 records an explicit skipped result with no score because no real-user cold-start
  embedding contract is approved yet.
- Layer 3 analyzes the new message as the focus and uses earlier messages only as context.

`DETECTIVES_STORAGE=memory` is convenient but disposable. Messages, jobs, and results disappear
when the backend stops. See the root [MongoDB instructions](README.md#optional-mongodb-persistence) for
persistent application data.

## 3. Configure Telegram

Complete [README-TDLIB.md](README-TDLIB.md) first. Create the ignored root configuration if
necessary:

```powershell
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}
```

Set these values in the root `.env` without committing them:

```dotenv
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TDJSON_PATH=telegram/.tdlib-build/install/bin/tdjson.dll
TDLIB_DATABASE_ENCRYPTION_KEY=your_existing_or_generated_key
TDLIB_USE_TEST_DC=false
```

An existing browser-managed login is restored from the ignored `telegram/.tdlib/web/` directory.
Do not run two backends against the same TDLib session database.

## 4. Start the backend

Open PowerShell terminal 1 at the repository root:

```powershell
.\scripts\start_demo.ps1
```

Expected output includes:

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8765
```

Keep this terminal open. The Layer 1 model loads lazily when the first referred message is
processed. On the current development machine, the first analysis can take about one minute and
use several gigabytes of memory.

## 5. Start the current frontend

Open PowerShell terminal 2:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Open:

```text
http://127.0.0.1:5174/
```

Do not substitute port 5173 if you want to restore the browser session previously created on
5174. The Vite development server proxies `/api` to `http://127.0.0.1:8765`.

## 6. Verify both processes

In a third PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
Invoke-RestMethod http://127.0.0.1:5174/api/health
```

Both calls should return `status: ok` and the same analyzer. For the complete real-user pipeline,
the analyzer string should include the Layer 1 version, `layer2-skipped-real-user-v1`, and the
focused Layer 3 version.

## 7. Test a new Telegram message

1. Open `http://127.0.0.1:5174/`.
2. Connect Telegram if the existing session is not restored.
3. Select the chat you want to test. Your self-chat is labeled **Saved Messages**.
4. Wait for its recent text history to load.
5. Send one new sanitized text message in that Telegram chat.
6. Wait for the frontend's five-second refresh and, on the first run, the lazy Layer 1 load.

Incoming and outgoing new text messages are eligible. The chat must be selected before the new
message arrives. Opening a chat imports up to 100 recent text messages as context only; imported
history intentionally receives no analysis jobs.

A message is highlighted only when the completed backend result is harmful. If Layer 1 returns
`not_cyberbully`, Layer 3 is intentionally not called and the message is not highlighted. Pending
and failed jobs are displayed separately and must not be interpreted as safe results.

## Stop the application

Press `Ctrl+C` in the frontend terminal and then in the backend terminal.

To inspect orphaned project listeners:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8765,5174 |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

Verify the process IDs before stopping them:

```powershell
Get-Process -Id <process_id>
Stop-Process -Id <process_id>
```

Stopping memory mode erases application messages and reports, but it does not delete the encrypted
browser-managed Telegram session.

## Verification commands

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
.\.venv\Scripts\ruff.exe check backend
```

Frontend:

```powershell
Push-Location frontend
npm run typecheck
npm run lint
npm run build
Pop-Location
```

Repository whitespace:

```powershell
git diff --check
```


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

## Common problems

### The frontend build is missing

Run `npm ci` and `npm run build` from `frontend/` before opening
`http://127.0.0.1:8765/demo/`. For live development, run Vite and use
`http://127.0.0.1:5174/`.

### Telegram shows your account name instead of Saved Messages

Refresh the current frontend. The self-chat uses Telegram's `is_saved_messages` metadata and is
labeled **Saved Messages**, regardless of the account profile name.

### A new message appears but has no analysis

Confirm that the chat was selected before the message arrived. Messages imported when a chat is
opened are historical context and are not analyzed retroactively.

### Analysis stays pending for a while

The first Layer 1 request loads the local model lazily. Wait for the visible pending/processing
state to complete before diagnosing the result.

### Layer 3 fails with a connection error

Confirm `OPENAI_API_KEY`, internet access, and that the backend was started from a normal terminal
with outbound network access. A successful local `/health` response does not prove API reachability.

### Vite fails with `spawn EPERM`

Run the frontend from a normal PowerShell terminal. Restricted sandboxes can block Vite's Windows
`net use` path-resolution check even when the installed Tailwind native module is valid.

### Port 8765 or 5174 is already in use

Use the listener inspection command in [Stop the application](#stop-the-application), verify the
owning process, and stop only the stale Detectives process.

### TDLib reports a locked database

Another backend or TDLib utility is using the same session database. Stop the other process; do
not delete `.env`, `telegram/.tdlib/`, or the native build.
