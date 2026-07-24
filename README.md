# tech4city

## Local application

Use [`DEMO.md`](DEMO.md) as the canonical startup guide for the combined backend/frontend,
sanitized four-chat seed data, optional MongoDB persistence, local Layer 1, and the default-deny
Telegram bridge. The fastest mode needs neither MongoDB nor a password:

```powershell
Set-Location backend
uv sync --dev
uv run uvicorn app.demo:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`.

## Architecture

The system design is documented in [`ARCHITECTURE.md`](ARCHITECTURE.md), with backend-specific
contracts in [`backend/README.md`](backend/README.md).

## Run Preprocessing

```sh
python -m utils.preprocess_confessit --input_file data/nusconfessit.json --output_file data/nus_processed.json
python -m utils.preprocess_confessit --input_file data/ntuconfessit.json --output_file data/ntu_processed.json
```

## Test TDLib

See [README-TDLIB.md](README-TDLIB.md) for the official-source TDLib build and interactive
Python user-account smoke tests. The bridge requires an explicit chat allowlist before it streams
new Telegram text messages; the TDLib guide documents the local two-process workflow.
