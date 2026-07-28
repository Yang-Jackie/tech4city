# Frontend

Build-free, read-only conversation review interface served by the FastAPI application:

- `index.html` defines chat discovery, conversation, and analysis drawer structure.
- `styles.css` defines the civic-blue responsive product UI.
- `app.js` receives live WebSocket notifications and uses REST snapshots, with
  polling only as a connection fallback.

The frontend has no package installation or build step. See the root
[`README.md`](../README.md) for setup, startup, optional integrations, and verification.
