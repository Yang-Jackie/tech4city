from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .models import AnalysisResult, Layer1Result, MessageCreate, StoredMessage

Analyzer = Callable[
    [MessageCreate, list[StoredMessage]],
    Awaitable[AnalysisResult],
]


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


def analyzer_version(analyzer: Analyzer) -> str:
    if analyzer is analyze_message:
        return "fake-v1"
    return str(getattr(analyzer, "pipeline_version", "custom"))
