# Standalone Python TDLib tests

This utility embeds the official TDLib JSON library in the Python process. It logs in as a
real Telegram user, shows the current account, loads chats, reads history without explicitly
marking it read, tests connectivity, and can send a confirmed message to Saved Messages.

TDLib source is pinned in `telegram/TDLIB_VERSION`. Source, native build output, the Python
virtual environment, credentials, logs, and the TDLib session database are local and ignored
by Git.

## 1. Build TDLib

The checked-in build script uses the available 64-bit MinGW toolchain and local Microsoft
vcpkg dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_tdlib.ps1
```

The runtime DLL and its dependencies are placed in:

```text
telegram/.tdlib-build/install/bin/
```

## 2. Create the Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tdlib.txt
```

## 3. Configure credentials

If `.env` does not exist, copy `.env.example` to it. In this configured workspace `.env`
already exists with a generated database key, so edit that existing file and add the
application credentials obtained from <https://my.telegram.org>:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_with_your_api_hash
```

If `TDLIB_DATABASE_ENCRYPTION_KEY` is empty, the CLI generates a cryptographically random key
and writes it to `.env` without displaying it. Keep this key together with the matching local
database. Losing it requires deleting `telegram/.tdlib/production/database/` and logging in
again.

Never commit `.env`, `.tdlib/`, or `.tdlib-build/`.

## 4. Run the interactive tests

```powershell
.\.venv\Scripts\python.exe -m telegram.cli
```

The first run follows TDLib's authorization states and can ask for a phone number, Telegram
login code, email verification, and two-step-verification password. These values are entered
interactively and are not saved by the Python utility. Registration and Premium purchases are
intentionally refused.

Later runs reuse the encrypted TDLib session database. Exit through menu item 6 when possible;
the utility calls `close`, not `logOut`, so the session remains authorized.

The send test targets only your own Saved Messages. It displays the exact generated text and
requires you to type `yes` before it sends anything.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

## Stream new text messages to the backend

The real-time bridge subscribes to TDLib's `updateNewMessage` events, forwards nonblank text
messages to the backend, and ignores media and other update types. Both incoming and outgoing
messages are forwarded so the backend can retain both sides of a conversation.

Start FastAPI first in one terminal:

```powershell
Set-Location backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If `uv` is unavailable, install the backend into the repository virtual environment once and use
that interpreter:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .\backend
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then start the bridge from the repository root in another terminal:

```powershell
.\.venv\Scripts\python.exe -m telegram.bridge
```

Send a new text message to Saved Messages from a Telegram client. A successful local flow prints
an identity-only delivery line similar to:

```text
Delivered message 100:100:123 (HTTP 202).
```

The three numbers are the Telegram account, chat, and message IDs. Use them to inspect the report:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/messages/123/report?telegram_account_id=100&chat_id=100"
```

Configure a different local backend or delivery timing in the ignored `.env`:

```dotenv
TECH4CITY_BACKEND_URL=http://127.0.0.1:8000
TECH4CITY_BRIDGE_TIMEOUT_SECONDS=10
TECH4CITY_BRIDGE_INITIAL_BACKOFF_SECONDS=0.5
TECH4CITY_BRIDGE_MAX_BACKOFF_SECONDS=30
```

This milestone is real-time only. Transient failures are retried in memory and block later
deliveries to preserve order, but a bridge process crash can still lose queued updates. A durable
outbox, historical backfill, and authenticated backend transport remain follow-up work.

## Security notes

- Treat `.env` and `telegram/.tdlib/` as account-session secrets.
- Do not run two processes against the same TDLib database directory.
- Revoke the generated Telegram session from Telegram's Devices settings if needed.
- Full phone numbers, login codes, passwords, API hashes, and the database key are not logged.
