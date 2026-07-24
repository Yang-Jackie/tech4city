from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py"
SPEC = importlib.util.spec_from_file_location("seed_demo", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
seed_demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed_demo)


def test_demo_seed_contains_four_sanitized_conversations() -> None:
    messages = seed_demo.build_demo_messages(900001)

    assert len(messages) == 12
    assert {message["chat_id"] for message in messages} == {
        910001,
        910002,
        910003,
        910004,
    }
    assert all(message["telegram_account_id"] == 900001 for message in messages)
    assert all(str(message["text"]).strip() for message in messages)
    assert all("@" not in str(message["text"]) for message in messages)
