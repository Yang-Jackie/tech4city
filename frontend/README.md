# Frontend

This folder contains the build-free, read-only conversation review interface:

- `index.html` defines chat discovery, conversation, and analysis drawer structure.
- `styles.css` defines the civic-blue responsive product UI.
- `app.js` polls chat summaries, messages, and selected-message reports.

Start the combined application from `backend/`:

```powershell
uv run uvicorn app.demo:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`. See [`../DEMO.md`](../DEMO.md) for sanitized seed data,
Layer 1, MongoDB, and Telegram bridge instructions.