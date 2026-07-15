from __future__ import annotations

from collections.abc import Awaitable, Callable

from .models import AnalysisResult, MessageCreate, StoredMessage

Analyzer = Callable[
    [MessageCreate, list[StoredMessage]],
    Awaitable[AnalysisResult],
]


async def analyze_message(
    message: MessageCreate,
    context: list[StoredMessage],
) -> AnalysisResult:
    '''Temporary boundary for the future ML-owned pipeline.'''
    _ = message, context
    return AnalysisResult(
        harmful=False,
        bully_probability=0,
        severity='none',
        categories=[],
        explanation='Fake analyzer only; no model evaluation was performed.',
        pipeline_version='fake-v1',
    )
