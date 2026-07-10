from __future__ import annotations

import inspect
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from transformers import AutoModelForSequenceClassification, AutoTokenizer


class Layer1:
    """Adapter for the local Roblox cyberbullying classifier."""

    DEFAULT_MODEL_DIR = Path("cyberbully-roblox-pii-lora-synbullying") / "best_model"
    LABEL2ID = {"normal": 0, "bully": 1}

    def __init__(
        self,
        model_dir: str | Path = DEFAULT_MODEL_DIR,
        *,
        normal_cutoff: float = 0.5,
        max_length: int = 256,
        device: Any | None = None,
    ) -> None:
        if not 0 <= normal_cutoff <= 1:
            raise ValueError("Expected 0 <= normal_cutoff <= 1")
        if max_length <= 0:
            raise ValueError("max_length must be positive")

        self.model_dir = self._resolve_model_dir(model_dir)
        self.normal_cutoff = normal_cutoff
        self.max_length = max_length
        self._device = device
        self._tokenizer = None
        self._model = None

    def predict(self, message: str) -> dict[str, Any]:
        """Classify one message as not cyberbullying or needing investigation."""
        if not isinstance(message, str):
            raise TypeError("message must be a string")

        self._ensure_loaded()

        import torch

        encoded = self._tokenizer(
            [message],
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        encoded = self._filter_model_inputs(self._model, encoded)
        encoded = {key: value.to(self._device) for key, value in encoded.items()}

        with torch.inference_mode():
            logits = self._model(**encoded).logits
            probs = torch.softmax(logits, dim=-1).squeeze(0).cpu()

        normal_score = float(probs[self.LABEL2ID["normal"]])
        bully_score = float(probs[self.LABEL2ID["bully"]])
        raw_label = self._raw_label(bully_score)
        status = "not_cyberbully" if bully_score < self.normal_cutoff else "need_to_investigate"

        return {
            "layer": 1,
            "status": status,
            "raw_label": raw_label,
            "normal_score": normal_score,
            "bully_score": bully_score,
            "model_dir": str(self.model_dir),
        }

    def _ensure_loaded(self) -> None:
        if self._tokenizer is not None and self._model is not None:
            return

        if self._device is None:
            self._device = self._best_device()

        self._tokenizer = self._load_tokenizer(self.model_dir)
        self._model = self._load_sequence_classifier(self.model_dir, self._device)
        self._model.eval()

    def _raw_label(self, bully_score: float) -> str:
        if bully_score < self.normal_cutoff:
            return "normal"
        return "uncertain"

    @staticmethod
    def _resolve_model_dir(model_dir: str | Path) -> Path:
        path = Path(model_dir)
        if path.is_absolute():
            return path
        file_relative_path = Path(__file__).resolve().parent / path
        if file_relative_path.exists():
            return file_relative_path
        return path

    @staticmethod
    def _best_device() -> Any:
        import torch

        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    @classmethod
    def _load_sequence_classifier(cls, model_dir: str | Path, device: Any) -> Any:
        model_dir = Path(model_dir)
        if (model_dir / "adapter_config.json").exists():
            try:
                from peft import AutoPeftModelForSequenceClassification
            except ImportError as exc:
                raise RuntimeError(
                    f"{model_dir} looks like a LoRA/PEFT adapter. Install peft first: python -m pip install peft"
                ) from exc

            print("loading PEFT/LoRA adapter:", model_dir)
            try:
                return AutoPeftModelForSequenceClassification.from_pretrained(str(model_dir)).to(device)
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                return cls._load_peft_adapter_with_compat_config(
                    AutoPeftModelForSequenceClassification,
                    model_dir,
                    device,
                )

        return AutoModelForSequenceClassification.from_pretrained(str(model_dir)).to(device)

    @staticmethod
    def _load_peft_adapter_with_compat_config(auto_peft_model_cls: Any, model_dir: Path, device: Any) -> Any:
        from peft import LoraConfig

        adapter_config_path = model_dir / "adapter_config.json"
        with adapter_config_path.open() as f:
            adapter_config = json.load(f)

        allowed_keys = set(inspect.signature(LoraConfig.__init__).parameters)
        compat_config = {
            key: value
            for key, value in adapter_config.items()
            if key in allowed_keys
        }
        removed_keys = sorted(set(adapter_config) - set(compat_config))

        with tempfile.TemporaryDirectory(prefix="peft_compat_") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            for item in model_dir.iterdir():
                target = tmp_dir / item.name
                if item.name == "adapter_config.json":
                    continue
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)

            with (tmp_dir / "adapter_config.json").open("w") as f:
                json.dump(compat_config, f, indent=2, sort_keys=True)
                f.write("\n")

            print("using PEFT compatibility config; removed keys:", removed_keys)
            return auto_peft_model_cls.from_pretrained(str(tmp_dir)).to(device)

    @staticmethod
    def _load_tokenizer(model_dir: str | Path) -> Any:
        model_dir = Path(model_dir)
        if (model_dir / "tokenizer_config.json").exists() or (model_dir / "tokenizer.json").exists():
            return AutoTokenizer.from_pretrained(str(model_dir))

        adapter_config_path = model_dir / "adapter_config.json"
        if adapter_config_path.exists():
            with adapter_config_path.open() as f:
                adapter_config = json.load(f)
            base_model = adapter_config.get("base_model_name_or_path")
            if base_model:
                print("loading tokenizer from PEFT base model:", base_model)
                return AutoTokenizer.from_pretrained(base_model)

        return AutoTokenizer.from_pretrained(str(model_dir))

    @staticmethod
    def _filter_model_inputs(model: Any, encoded: dict[str, Any]) -> dict[str, Any]:
        signature = inspect.signature(model.forward)
        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
            return encoded
        forward_params = set(signature.parameters)
        return {key: value for key, value in encoded.items() if key in forward_params}


__all__ = ["Layer1"]
