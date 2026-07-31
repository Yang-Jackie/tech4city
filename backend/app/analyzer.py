from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .models import (
    AnalysisResult,
    Layer1Result,
    Layer2Result,
    Layer3Result,
    MessageCreate,
    StoredMessage,
)

Analyzer = Callable[
    [MessageCreate, list[StoredMessage]],
    Awaitable[AnalysisResult],
]

LAYER1_CONTINUE_STATUS = "need_to_investigate"


async def analyze_message(
    message: MessageCreate,
    context: list[StoredMessage],
) -> AnalysisResult:
    """Temporary boundary for the future ML-owned pipeline."""
    _ = message, context
    return AnalysisResult(
        harmful=False,
        bully_probability=0,
        severity="none",
        categories=[],
        explanation="Fake analyzer only; no model evaluation was performed.",
        pipeline_version="fake-v1",
    )


class Layer1Analyzer:
    """Async backend adapter for the existing synchronous Layer 1 classifier."""

    def __init__(
        self,
        *,
        pipeline_version: str,
        model_dir: Path | None = None,
        layer_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.pipeline_version = pipeline_version
        self._model_dir = model_dir
        self._layer_factory = layer_factory or self._build_layer
        self._layer: Any | None = None

    async def __call__(
        self,
        message: MessageCreate,
        context: list[StoredMessage],
    ) -> AnalysisResult:
        _ = context
        raw_result = await asyncio.to_thread(self._predict, message.text)
        return AnalysisResult(
            pipeline_version=self.pipeline_version,
            layer1=Layer1Result(
                status=raw_result["status"],
                raw_label=raw_result["raw_label"],
                normal_score=raw_result["normal_score"],
                bully_score=raw_result["bully_score"],
            ),
        )

    def _predict(self, text: str) -> dict[str, Any]:
        if self._layer is None:
            self._layer = self._layer_factory()
        return self._layer.predict(text)

    def _build_layer(self) -> Any:
        source_path = Path(__file__).resolve().parents[2] / "Layer" / "Layer1.py"
        spec = importlib.util.spec_from_file_location(
            "_tech4city_layer1_adapter", source_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load Layer 1 from {source_path}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ImportError as exc:
            raise RuntimeError(
                "Layer 1 dependencies are unavailable. Run `uv sync --extra ml` "
                "from backend/."
            ) from exc

        layer1_kwargs: dict[str, Any] = {}
        if self._model_dir is not None:
            layer1_kwargs["model_dir"] = self._model_dir
        return module.Layer1(**layer1_kwargs)


class Layer2Analyzer:
    """Research adapter for the existing Layer 2 classifier."""

    def __init__(
        self,
        *,
        pipeline_version: str,
        classifier_head_path: Path,
        text_embedding_model: str,
        layer_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.pipeline_version = pipeline_version
        self._classifier_head_path = classifier_head_path
        self._text_embedding_model = text_embedding_model
        self._layer_factory = layer_factory or self._build_layer
        self._layer: Any | None = None

    async def __call__(
        self,
        message: MessageCreate,
        context: list[StoredMessage],
    ) -> AnalysisResult:
        _ = context
        raw_result = await asyncio.to_thread(self._predict, message.text)
        return AnalysisResult(
            pipeline_version=self.pipeline_version,
            layer2=Layer2Result(
                status=raw_result["status"],
                raw_label=raw_result["raw_label"],
                normal_score=raw_result["normal_score"],
                bully_score=raw_result["bully_score"],
                user_embedding_strategy=raw_result["user_embedding_strategy"],
            ),
        )

    def _predict(self, text: str) -> dict[str, Any]:
        if self._layer is None:
            self._layer = self._layer_factory()
        return self._layer.predict(text, None)

    def _build_layer(self) -> Any:
        source_path = Path(__file__).resolve().parents[2] / "Layer" / "Layer2.py"
        spec = importlib.util.spec_from_file_location(
            "_tech4city_layer2_adapter", source_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load Layer 2 from {source_path}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ImportError as exc:
            raise RuntimeError(
                "Layer 2 dependencies are unavailable. Run "
                "`uv sync --extra ml --extra layer2` from the repository root."
            ) from exc
        return module.Layer2(
            classifier_head_model_path=self._classifier_head_path,
            node2vec_embedding_path=None,
            text_embedding_model=self._text_embedding_model,
        )


class Layer2SkippedAnalyzer:
    """No-score Layer 2 stage used until real-user cold start is specified."""

    def __init__(self, *, pipeline_version: str) -> None:
        self.pipeline_version = pipeline_version

    async def __call__(
        self,
        message: MessageCreate,
        context: list[StoredMessage],
    ) -> AnalysisResult:
        _ = message, context
        return AnalysisResult(
            pipeline_version=self.pipeline_version,
            layer2=Layer2Result(
                status="skipped",
                skip_reason="real_user_embedding_unavailable",
            ),
        )


class Layer1Layer2Analyzer:
    """Gate the Layer 2 stage on the existing Layer 1 decision."""

    def __init__(
        self,
        layer1: Layer1Analyzer,
        layer2: Analyzer,
    ) -> None:
        self._layer1 = layer1
        self._layer2 = layer2
        self.pipeline_version = f"{layer1.pipeline_version}+{layer2.pipeline_version}"

    async def __call__(
        self,
        message: MessageCreate,
        context: list[StoredMessage],
    ) -> AnalysisResult:
        layer1_result = await self._layer1(message, context)
        if layer1_result.layer1.status != LAYER1_CONTINUE_STATUS:
            return AnalysisResult(
                pipeline_version=self.pipeline_version,
                layer1=layer1_result.layer1,
                layer2=Layer2Result(
                    status="skipped",
                    skip_reason="layer1_not_referred",
                ),
            )
        layer2_result = await self._layer2(message, context)
        return AnalysisResult(
            pipeline_version=self.pipeline_version,
            layer1=layer1_result.layer1,
            layer2=layer2_result.layer2,
        )


class Layer3Analyzer:
    """Analyze one new message with earlier chronological messages as context."""

    def __init__(
        self,
        *,
        pipeline_version: str,
        model: str,
        layer_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.pipeline_version = pipeline_version
        self.model = model
        self._layer_factory = layer_factory or self._build_layer
        self._layer: Any | None = None

    async def __call__(
        self,
        message: MessageCreate,
        context: list[StoredMessage],
    ) -> AnalysisResult:
        conversation = {
            "messages": [
                self._conversation_message(item) for item in [*context, message]
            ],
            "focus_message_id": str(message.message_id),
        }
        raw_result = await asyncio.to_thread(self._explain, conversation)
        layer3 = Layer3Result.model_validate(raw_result)
        analysis = layer3.analysis
        return AnalysisResult(
            harmful=analysis.is_suspected_cyberbullying,
            severity=analysis.severity,
            categories=[category.label for category in analysis.categories],
            explanation=analysis.explanation_for_target,
            pipeline_version=self.pipeline_version,
            layer3=layer3,
        )

    def _explain(self, conversation: dict[str, Any]) -> dict[str, Any]:
        if self._layer is None:
            self._layer = self._layer_factory()
        return self._layer.explain(conversation)

    @staticmethod
    def _conversation_message(message: MessageCreate) -> dict[str, str]:
        return {
            "message_id": str(message.message_id),
            "timestamp": message.sent_at.isoformat(),
            "sender_id": str(message.sender_id),
            "message": message.text,
        }

    def _build_layer(self) -> Any:
        source_path = Path(__file__).resolve().parents[2] / "Layer" / "Layer3.py"
        spec = importlib.util.spec_from_file_location(
            "_tech4city_layer3_adapter", source_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load Layer 3 from {source_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Layer3(model=self.model)


class Layer1Layer2Layer3Analyzer:
    """Run Layer 3 only when Layer 1 refers the new message onward."""

    def __init__(
        self,
        layer1_layer2: Layer1Layer2Analyzer,
        layer3: Layer3Analyzer,
    ) -> None:
        self._layer1_layer2 = layer1_layer2
        self._layer3 = layer3
        self.pipeline_version = (
            f"{layer1_layer2.pipeline_version}+{layer3.pipeline_version}"
        )

    async def __call__(
        self,
        message: MessageCreate,
        context: list[StoredMessage],
    ) -> AnalysisResult:
        local_result = await self._layer1_layer2(message, context)
        if local_result.layer1.status != LAYER1_CONTINUE_STATUS:
            return local_result.model_copy(
                update={"pipeline_version": self.pipeline_version}
            )
        layer3_result = await self._layer3(message, context)
        return layer3_result.model_copy(
            update={
                "pipeline_version": self.pipeline_version,
                "layer1": local_result.layer1,
                "layer2": local_result.layer2,
            }
        )


def analyzer_version(analyzer: Analyzer) -> str:
    if analyzer is analyze_message:
        return "fake-v1"
    return str(getattr(analyzer, "pipeline_version", "custom"))
