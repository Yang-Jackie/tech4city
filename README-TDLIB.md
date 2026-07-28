# Standalone Python TDLib tests

This utility embeds the official TDLib JSON library in the Python process. It logs in as a
real Telegram user, shows the current account, loads chats, reads history without explicitly
marking it read, tests connectivity, and can send a confirmed message to Saved Messages.

TDLib source is pinned in `telegram/TDLIB_VERSION`. Source, native build output, the Python
virtual environment, credentials, logs, and the TDLib session database are local and ignored
by Git.

## Prerequisites

The checked-in build workflow targets 64-bit Windows. Install these tools and ensure each command
is on `PATH`:

- Git.
- CMake.
- Ninja.
- A 64-bit MinGW toolchain providing `gcc` and `g++`.
- PowerShell 5.1 or newer.

You can check the native build tools before starting:

```powershell
Get-Command git, cmake, ninja, gcc, g++
```

The first build clones the pinned TDLib and vcpkg sources, downloads native dependencies, and can
take considerable time and disk space.

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

## 2. Prepare the Python environment

Complete the root [first-time setup](README.md#first-time-setup). It creates the unified `.venv`
used by the application, bridge, and interactive TDLib utility.

## 3. Configure credentials

If `.env` does not exist, copy the safe example from the repository root:

```powershell
Copy-Item .env.example .env
```

Edit the ignored `.env` and add the application credentials obtained from
<https://my.telegram.org>:

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

The root [verification command](README.md#verify) includes the offline TDLib and bridge test
suites.

## Use TDLib with the application

After the native library and credentials are ready, start the application and follow the root
[browser-managed Telegram guide](README.md#connect-telegram-from-the-frontend). The backend owns
one isolated TDLib client per browser-connected account and currently imports and streams Saved
Messages only.

## Security notes

- Treat `.env` and `telegram/.tdlib/` as account-session secrets.
- Do not run two processes against the same TDLib database directory.
- Revoke the generated Telegram session from Telegram's Devices settings if needed.
- Full phone numbers, login codes, passwords, API hashes, and the database key are not logged.
