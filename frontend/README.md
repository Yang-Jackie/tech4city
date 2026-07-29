# Frontend

Build-free, read-only conversation review interface served by the FastAPI application:

- `index.html` defines chat discovery, conversation, and analysis drawer structure.
- `styles.css` defines the civic-blue responsive product UI.
- `app.js` lists TDLib chats, explicitly opens a selected chat to start analysis,
  receives live WebSocket notifications, and uses REST snapshots with polling
  only as a connection fallback.

Telegram chat selection is session-only. The frontend does not write the selected
chat ID to local storage or keep it in the URL.

The frontend has no package installation or build step. See the root
[`README.md`](../README.md) for setup, startup, optional integrations, and verification.
