# Detectives frontend

React application for reviewing selected Telegram text conversations and their available analysis.
It is the user interface for **Detectives**, a Tech4City hackathon submission.
The frontend does not include demo conversations or model-quality claims.

## Stack

- React 19 and TypeScript
- Vite 8
- Tailwind CSS 4
- shadcn/ui with Radix primitives

## Local development

Start the FastAPI backend on port 8765, then run:

```powershell
Set-Location frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Open `http://127.0.0.1:5174/`. The Vite server proxies `/api` to
`http://127.0.0.1:8765`. Set `VITE_DEV_BACKEND_URL` to use another local backend.

A first-time visitor sees Telegram connection onboarding. The browser stores only the opaque login
session ID; the backend owns the HttpOnly authorization cookie and TDLib session database.

## Production build

```powershell
Set-Location frontend
npm ci
npm run build
```

The ignored `frontend/dist/` directory contains the production assets. When it exists,
`app.demo:app` serves it at `/demo/`. Production builds use same-origin backend routes by
default. Set `VITE_API_BASE_URL` only when deploying the frontend and backend on different
origins.

## Verification

```powershell
npm run typecheck
npm run lint
npm run build
```

The application imports shared frontend contracts from `src/data/models.ts`. Do not add private
conversation fixtures, Telegram credentials, session identifiers, or local TDLib data to this
directory.
