from __future__ import annotations

from typing import Any

try:
    from .Layer1 import Layer1
    from .Layer3 import Layer3
except ImportError:  # Allows running this file directly from inside the folder.
    from Layer1 import Layer1
    from Layer3 import Layer3


class Layer:
    """Public API that composes the three cyberbullying analysis layers."""

    def __init__(
        self,
        *,
        layer1: Layer1 | None = None,
        layer3: Layer3 | None = None,
        layer1_kwargs: dict[str, Any] | None = None,
        layer3_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._layer1 = layer1 if layer1 is not None else Layer1(**(layer1_kwargs or {}))
        self._layer3 = layer3 if layer3 is not None else Layer3(**(layer3_kwargs or {}))

    def layer1(self, message: str) -> dict[str, Any]:
        return self._layer1.predict(message)

    def layer2(self, conversation: Any) -> dict[str, Any]:
        return {}

    def layer3(self, conversation: Any, **kwargs: Any) -> dict[str, Any]:
        return self._layer3.explain(conversation, **kwargs)


__all__ = ["Layer"]
