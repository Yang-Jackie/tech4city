from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_dataset_demo.py"
SPEC = importlib.util.spec_from_file_location("seed_dataset_demo", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
seed_dataset_demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed_dataset_demo)


def test_dataset_seed_uses_four_generated_conversations() -> None:
    messages, conversations = seed_dataset_demo.build_dataset_messages(900101)

    assert len(conversations) == 4
    assert len(messages) == 54
    assert {message["chat_id"] for message in messages} == {
        930001,
        930002,
        930003,
        930004,
    }
    assert all(message["telegram_account_id"] == 900101 for message in messages)
    assert all(str(message["text"]).strip() for message in messages)
    assert all(conversation["scenario"] for conversation in conversations)


def test_dataset_seed_stops_before_submitting_another_message_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [
        {
            "telegram_account_id": 900101,
            "chat_id": 930001,
            "message_id": message_id,
            "sender_id": 1,
            "text": f"Sanitized message {message_id}",
            "sent_at": "2026-07-25T09:00:00Z",
        }
        for message_id in (1, 2)
    ]
    post_ids: list[int] = []

    def fake_request(method: str, _url: str, payload=None):
        if method == "GET" and _url.endswith("/health"):
            return 200, {"storage": "memory", "analyzer": "full-test"}
        if method == "POST":
            post_ids.append(payload["message_id"])
            return 202, {}
        return 200, {"analysis_job": {"status": "failed"}}

    monkeypatch.setattr(
        seed_dataset_demo,
        "build_dataset_messages",
        lambda _account_id: (messages, []),
    )
    monkeypatch.setattr(seed_dataset_demo, "request_json", fake_request)

    with pytest.raises(RuntimeError, match="chat 930001, message 1"):
        seed_dataset_demo.seed("http://backend.test", 900101, timeout=1)

    assert post_ids == [1]
