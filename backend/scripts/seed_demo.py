"""Seed four sanitized conversations through the public backend API."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_SENT_AT = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
CHAT_SCENARIOS = (
    (
        910001,
        (
            (True, "Would Tuesday afternoon work for the planning call?"),
            (False, "Yes, I can join at 3 PM."),
            (True, "Great, I will prepare a short agenda."),
        ),
    ),
    (
        910002,
        (
            (False, "I disagree with your suggestion."),
            (True, "Let us compare the two options before deciding."),
            (False, "Your ideas are stupid and nobody cares what you think."),
        ),
    ),
    (
        910003,
        (
            (True, "That response sounded sarcastic to me."),
            (False, "I meant it as a joke, but I see why it landed badly."),
            (True, "Thanks for explaining. Let us reset."),
        ),
    ),
    (
        910004,
        (
            (False, "I am frustrated because I do not feel heard."),
            (True, "Let us pause and continue when we are both calm."),
            (False, "Okay, I am sorry. We can try again tomorrow."),
        ),
    ),
)


def build_demo_messages(account_id: int) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    minute = 0
    for scenario_index, (chat_id, entries) in enumerate(CHAT_SCENARIOS, start=1):
        other_sender = 920000 + scenario_index
        for message_id, (outgoing, text) in enumerate(entries, start=1):
            sent_at = BASE_SENT_AT + timedelta(minutes=minute)
            minute += 1
            messages.append(
                {
                    "telegram_account_id": account_id,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "sender_id": account_id if outgoing else other_sender,
                    "text": text,
                    "sent_at": sent_at.isoformat().replace("+00:00", "Z"),
                }
            )
    return messages


def request_json(
    method: str,
    url: str,
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Backend returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            f"Could not reach the backend at {url}: {exc.reason}"
        ) from exc


def seed(base_url: str, account_id: int, *, wait: bool, timeout: float) -> None:
    base_url = base_url.rstrip("/")
    status, health = request_json("GET", f"{base_url}/health")
    if status != 200:
        raise RuntimeError(f"Backend health check returned HTTP {status}")
    print(
        f"Backend ready: storage={health.get('storage')} "
        f"analyzer={health.get('analyzer')}"
    )

    messages = build_demo_messages(account_id)
    pending: list[dict[str, object]] = []
    for message in messages:
        status, _ = request_json("POST", f"{base_url}/messages", message)
        if status not in {200, 202}:
            raise RuntimeError(f"Message ingestion returned HTTP {status}")
        pending.append(message)
    print(
        f"Seeded {len(messages)} sanitized messages across {len(CHAT_SCENARIOS)} chats."
    )

    if wait:
        deadline = time.monotonic() + timeout
        remaining = {(item["chat_id"], item["message_id"]) for item in pending}
        while remaining:
            completed: set[tuple[object, object]] = set()
            for chat_id, message_id in remaining:
                query = urlencode(
                    {"telegram_account_id": account_id, "chat_id": chat_id}
                )
                _, report = request_json(
                    "GET",
                    f"{base_url}/messages/{message_id}/report?{query}",
                )
                job_status = report["analysis_job"]["status"]
                if job_status == "failed":
                    raise RuntimeError(
                        f"Analysis failed for chat {chat_id}, message {message_id}"
                    )
                if job_status == "completed":
                    completed.add((chat_id, message_id))
            remaining -= completed
            if remaining and time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Timed out with {len(remaining)} analysis job(s) unfinished"
                )
            if remaining:
                time.sleep(0.25)
        print("All analysis jobs completed.")

    query = urlencode({"telegram_account_id": account_id})
    print(f"Open {base_url}/demo/?{query}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--account-id", type=int, default=900001)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Return after ingestion instead of waiting for analysis.",
    )
    args = parser.parse_args()
    try:
        seed(
            args.base_url,
            args.account_id,
            wait=not args.no_wait,
            timeout=args.timeout,
        )
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
