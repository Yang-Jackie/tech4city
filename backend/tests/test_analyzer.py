from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from app.analyzer import (
    Layer1Analyzer,
    Layer1Layer2Analyzer,
    Layer1Layer2Layer3Analyzer,
    Layer2Analyzer,
    Layer2SkippedAnalyzer,
    Layer3Analyzer,
)
from app.config import Settings
from app.main import build_analyzer
from app.models import MessageCreate, StoredMessage


def load_layer3_module():
    source_path = Path(__file__).resolve().parents[2] / "Layer" / "Layer3.py"
    spec = importlib.util.spec_from_file_location("_test_layer3_contract", source_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def layer3_output() -> dict[str, object]:
    analysis = {
        "is_suspected_cyberbullying": False,
        "confidence": 0.1,
        "severity": "none",
        "target_user_ids": [],
        "suspected_actor_user_ids": [],
        "categories": [
            {
                "label": "not_cyberbullying",
                "evidence_strength": "direct",
                "message_ids": ["300"],
                "why": "The sanitized message is neutral.",
            }
        ],
        "evidence": [],
        "pattern_analysis": {
            "is_targeted": False,
            "is_repeated": False,
            "shows_escalation": False,
            "has_power_or_group_dynamic": False,
            "notes": "No harmful pattern in the supplied context.",
        },
        "explanation_for_target": "No cyberbullying pattern is evident.",
        "uncertainty": ["Only two sanitized messages were supplied."],
        "recommended_next_steps": [],
    }
    return {
        "layer": 3,
        "explanation": analysis["explanation_for_target"],
        "analysis": analysis,
        "model": "layer3-test-model",
    }


def test_layer3_contract_defaults_focus_to_latest_message() -> None:
    module = load_layer3_module()

    payload = module.normalize_conversation_input(
        [
            {"message_id": 299, "sender_id": 401, "message": "Earlier message"},
            {"message_id": 300, "sender_id": 400, "message": "New message"},
        ]
    )

    assert payload["focus_message_id"] == "300"
    assert "Evaluate only the message identified by focus_message_id" in (
        module.CYBERBULLYING_ANALYST_PROMPT
    )


class FakeLayer1:
    def __init__(self, status: str = "need_to_investigate") -> None:
        self.calls: list[str] = []
        self.status = status

    def predict(self, text: str) -> dict[str, object]:
        self.calls.append(text)
        return {
            "layer": 1,
            "status": self.status,
            "raw_label": (
                "uncertain" if self.status == "need_to_investigate" else "normal"
            ),
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


class FakeLayer2:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def predict(self, text: str, user_id: int | None) -> dict[str, object]:
        self.calls.append((text, user_id))
        return {
            "status": "normal",
            "raw_label": "normal",
            "normal_score": 0.55,
            "bully_score": 0.45,
            "user_embedding_strategy": "zero",
        }


def test_layer2_adapter_uses_zero_user_contract() -> None:
    layer = FakeLayer2()
    analyzer = Layer2Analyzer(
        pipeline_version="layer2-test-v1",
        classifier_head_path=Path("unused-test-head.pth"),
        text_embedding_model="unused-test-encoder",
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

    result = asyncio.run(analyzer(message, []))

    assert layer.calls == [(message.text, None)]
    assert result.pipeline_version == "layer2-test-v1"
    assert result.layer1 is None
    assert result.layer2.model_dump() == {
        "status": "normal",
        "raw_label": "normal",
        "normal_score": 0.55,
        "bully_score": 0.45,
        "user_embedding_strategy": "zero",
        "skip_reason": None,
    }


def test_combined_adapter_preserves_both_raw_outputs() -> None:
    layer1 = FakeLayer1()
    layer2 = FakeLayer2()
    analyzer = Layer1Layer2Analyzer(
        Layer1Analyzer(
            pipeline_version="layer1-test-v1",
            layer_factory=lambda: layer1,
        ),
        Layer2Analyzer(
            pipeline_version="layer2-test-v1",
            classifier_head_path=Path("unused-test-head.pth"),
            text_embedding_model="unused-test-encoder",
            layer_factory=lambda: layer2,
        ),
    )
    message = MessageCreate(
        telegram_account_id=100,
        chat_id=200,
        message_id=300,
        sender_id=400,
        text="Sanitized test message",
        sent_at=datetime(2026, 7, 19, tzinfo=UTC),
    )

    result = asyncio.run(analyzer(message, []))

    assert result.pipeline_version == "layer1-test-v1+layer2-test-v1"
    assert result.layer1 is not None
    assert result.layer2 is not None
    assert result.harmful is None
    assert result.explanation is None


def test_runtime_settings_build_combined_analyzer_without_loading_models() -> None:
    settings = Settings(
        storage="memory",
        mongodb_uri=None,
        mongodb_database="detectives_test",
        analyzer="layer1-layer2",
    )

    analyzer = build_analyzer(settings)

    assert isinstance(analyzer, Layer1Layer2Analyzer)
    assert analyzer.pipeline_version == (
        "layer1-roblox-pii-lora-synbullying-v1+layer2-skipped-real-user-v1"
    )


class FakeLayer3:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def explain(self, conversation: dict[str, object]) -> dict[str, object]:
        self.calls.append(conversation)
        return layer3_output()


def test_layer3_adapter_passes_chronological_context_and_maps_existing_output() -> None:
    layer = FakeLayer3()
    analyzer = Layer3Analyzer(
        pipeline_version="layer3-test-v1",
        model="layer3-test-model",
        layer_factory=lambda: layer,
    )
    context = [
        StoredMessage(
            telegram_account_id=100,
            chat_id=200,
            message_id=299,
            sender_id=401,
            text="Earlier sanitized message",
            sent_at=datetime(2026, 7, 19, 9, tzinfo=UTC),
            received_at=datetime(2026, 7, 19, 9, 0, 1, tzinfo=UTC),
        )
    ]
    message = MessageCreate(
        telegram_account_id=100,
        chat_id=200,
        message_id=300,
        sender_id=400,
        text="Current sanitized message",
        sent_at=datetime(2026, 7, 19, 10, tzinfo=UTC),
    )

    result = asyncio.run(analyzer(message, context))

    messages = layer.calls[0]["messages"]
    assert isinstance(messages, list)
    assert [item["message_id"] for item in messages] == ["299", "300"]
    assert [item["sender_id"] for item in messages] == ["401", "400"]
    assert layer.calls[0]["focus_message_id"] == "300"
    assert result.pipeline_version == "layer3-test-v1"
    assert result.harmful is False
    assert result.bully_probability is None
    assert result.severity == "none"
    assert result.categories == ["not_cyberbullying"]
    assert result.explanation == "No cyberbullying pattern is evident."
    assert result.layer3 is not None
    assert result.layer3.analysis.pattern_analysis.is_repeated is False


def test_all_layers_adapter_preserves_local_and_conversation_outputs() -> None:
    layer1 = FakeLayer1()
    layer3 = FakeLayer3()
    local = Layer1Layer2Analyzer(
        Layer1Analyzer(
            pipeline_version="layer1-test-v1",
            layer_factory=lambda: layer1,
        ),
        Layer2SkippedAnalyzer(pipeline_version="layer2-skipped-test-v1"),
    )
    analyzer = Layer1Layer2Layer3Analyzer(
        local,
        Layer3Analyzer(
            pipeline_version="layer3-test-v1",
            model="layer3-test-model",
            layer_factory=lambda: layer3,
        ),
    )
    message = MessageCreate(
        telegram_account_id=100,
        chat_id=200,
        message_id=300,
        sender_id=400,
        text="Sanitized test message",
        sent_at=datetime(2026, 7, 19, tzinfo=UTC),
    )

    result = asyncio.run(analyzer(message, []))

    assert result.pipeline_version == (
        "layer1-test-v1+layer2-skipped-test-v1+layer3-test-v1"
    )
    assert result.layer1 is not None
    assert result.layer2 is not None
    assert result.layer2.status == "skipped"
    assert result.layer2.bully_score is None
    assert result.layer2.skip_reason == "real_user_embedding_unavailable"
    assert result.layer3 is not None
    assert result.explanation == "No cyberbullying pattern is evident."


def test_all_layers_stop_after_layer1_clear_result() -> None:
    layer1 = FakeLayer1(status="not_cyberbully")
    layer3 = FakeLayer3()
    local = Layer1Layer2Analyzer(
        Layer1Analyzer(
            pipeline_version="layer1-test-v1",
            layer_factory=lambda: layer1,
        ),
        Layer2SkippedAnalyzer(pipeline_version="layer2-skipped-test-v1"),
    )
    analyzer = Layer1Layer2Layer3Analyzer(
        local,
        Layer3Analyzer(
            pipeline_version="layer3-test-v1",
            model="layer3-test-model",
            layer_factory=lambda: layer3,
        ),
    )
    message = MessageCreate(
        telegram_account_id=100,
        chat_id=200,
        message_id=300,
        sender_id=400,
        text="Sanitized test message",
        sent_at=datetime(2026, 7, 19, tzinfo=UTC),
    )

    result = asyncio.run(analyzer(message, []))

    assert result.layer1 is not None
    assert result.layer1.status == "not_cyberbully"
    assert result.layer2 is not None
    assert result.layer2.status == "skipped"
    assert result.layer2.skip_reason == "layer1_not_referred"
    assert result.layer3 is None
    assert layer3.calls == []


def test_runtime_settings_build_layer3_modes_without_loading_clients() -> None:
    direct = build_analyzer(
        Settings(
            storage="memory",
            mongodb_uri=None,
            mongodb_database="detectives_test",
            analyzer="layer3",
        )
    )
    combined = build_analyzer(
        Settings(
            storage="memory",
            mongodb_uri=None,
            mongodb_database="detectives_test",
            analyzer="layer1-layer2-layer3",
        )
    )

    assert isinstance(direct, Layer3Analyzer)
    assert direct.pipeline_version == "layer3-chatgpt-answer-v1"
    assert isinstance(combined, Layer1Layer2Layer3Analyzer)
    assert combined.pipeline_version.endswith("+layer3-chatgpt-answer-v1")
