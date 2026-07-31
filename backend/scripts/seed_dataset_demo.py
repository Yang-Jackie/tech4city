"""Seed four generated dataset conversations through the public backend API."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from seed_demo import request_json  # noqa: E402

BASE_SENT_AT = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)
DATASET_PATH = REPOSITORY_ROOT / "data" / "nus_synbullying_small.json"
CONVERSATION_SELECTIONS = (
    ("A", 17, 930001),
    ("E", 0, 930002),
    ("A", 1, 930003),
    ("B", 0, 930004),
)


def load_selected_conversations(
    dataset_path: Path = DATASET_PATH,
) -> list[dict[str, Any]]:
    with dataset_path.open(encoding="utf-8") as dataset_file:
        dataset = json.load(dataset_file)

    selected: list[dict[str, Any]] = []
    for category, index, chat_id in CONVERSATION_SELECTIONS:
        conversation = dataset[category][index]
        selected.append(
            {
                "category": category,
                "source_index": index,
                "chat_id": chat_id,
                "scenario": conversation["scenario"],
                "messages": conversation["messages"],
            }
        )
    return selected


def build_dataset_messages(
    account_id: int,
    dataset_path: Path = DATASET_PATH,
) -> tuple[list[dict[str, object]], list[dict[str, Any]]]:
    conversations = load_selected_conversations(dataset_path)
    messages: list[dict[str, object]] = []
    sent_at = BASE_SENT_AT

    for conversation in conversations:
        speaker_ids: dict[str, int] = {}
        for message_id, source_message in enumerate(conversation["messages"], start=1):
            speaker = str(source_message["speaker"])
            if speaker not in speaker_ids:
                speaker_ids[speaker] = (
                    int(conversation["chat_id"]) * 100 + len(speaker_ids) + 1
                )
            messages.append(
                {
                    "telegram_account_id": account_id,
                    "chat_id": conversation["chat_id"],
                    "message_id": message_id,
                    "sender_id": speaker_ids[speaker],
                    "text": source_message["text"],
                    "sent_at": sent_at.isoformat().replace("+00:00", "Z"),
                }
            )
            sent_at += timedelta(minutes=1)

    return messages, conversations


def seed(base_url: str, account_id: int, *, timeout: float) -> None:
    base_url = base_url.rstrip("/")
    status, health = request_json("GET", f"{base_url}/health")
    if status != 200:
        raise RuntimeError(f"Backend health check returned HTTP {status}")
    if health.get("analyzer") == "fake":
        raise RuntimeError("Backend is using the fake analyzer, not Layer 1")
    print(
        f"Backend ready: storage={health.get('storage')} "
        f"analyzer={health.get('analyzer')}"
    )

    messages, conversations = build_dataset_messages(account_id)
    deadline = time.monotonic() + timeout
    for message in messages:
        status, _ = request_json("POST", f"{base_url}/messages", message)
        if status not in {200, 202}:
            raise RuntimeError(f"Message ingestion returned HTTP {status}")
        _wait_for_analysis(base_url, message, deadline=deadline)

    print(
        f"Seeded {len(messages)} generated-dataset messages across "
        f"{len(conversations)} chats."
    )
    for conversation in conversations:
        print(
            f"  chat {conversation['chat_id']}: "
            f"{conversation['scenario']} "
            f"({len(conversation['messages'])} messages)"
        )

    print("All analysis jobs completed.")
    query = urlencode({"telegram_account_id": account_id})
    print(f"Open {base_url}/demo/?{query}")


def _wait_for_analysis(
    base_url: str,
    message: dict[str, object],
    *,
    deadline: float,
) -> None:
    chat_id = message["chat_id"]
    message_id = message["message_id"]
    query = urlencode(
        {
            "telegram_account_id": message["telegram_account_id"],
            "chat_id": chat_id,
        }
    )
    while True:
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
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Timed out waiting for chat {chat_id}, message {message_id}"
            )
        time.sleep(0.25)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--account-id", type=int, default=900101)
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    try:
        seed(args.base_url, args.account_id, timeout=args.timeout)
    except (OSError, KeyError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
