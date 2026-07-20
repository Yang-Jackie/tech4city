from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.analyzer import Layer1Analyzer
from app.models import MessageCreate


class FakeLayer1:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def predict(self, text: str) -> dict[str, object]:
        self.calls.append(text)
        return {
            "layer": 1,
            "status": "need_to_investigate",
            "raw_label": "uncertain",
            "normal_score": 0.2,
            "bully_score": 0.8,
            "model_dir": "sanitized-model-path",
        }


def test_layer1_adapter_preserves_raw_contract_without_inventing_findings() -> None:
    layer = FakeLayer1()
    analyzer = Layer1Analyzer(
        pipeline_version="layer1-test-v1",
        layer_factory=lambda: layer,
    )
    message = MessageCreate(
        telegram_account_id=100,
        chat_id=200,
        message_id=300,
        sender_id=400,
        text="Sanitized test message",
        sent_at=datetime(2026, 7, 19, tzinfo=UTC),
    )

    first = asyncio.run(analyzer(message, []))
    second = asyncio.run(analyzer(message, []))

    assert layer.calls == [message.text, message.text]
    assert first.pipeline_version == "layer1-test-v1"
    assert first.harmful is None
    assert first.bully_probability is None
    assert first.severity is None
    assert first.categories is None
    assert first.explanation is None
    assert first.layer1.model_dump() == {
        "status": "need_to_investigate",
        "raw_label": "uncertain",
        "normal_score": 0.2,
        "bully_score": 0.8,
    }
    assert second.layer1 == first.layer1
