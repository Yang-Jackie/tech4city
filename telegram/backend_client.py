"""Small synchronous HTTP client for the local FastAPI ingestion boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .normalization import NormalizedMessage


class BackendUnavailable(ConnectionError):
    """The backend could not be reached or returned an unreadable response."""


@dataclass(frozen=True)
class BackendResponse:
    status_code: int
    body: dict[str, Any] | None

    @property
    def accepted(self) -> bool:
        return self.status_code in {200, 202}

    @property
    def transient(self) -> bool:
        return self.status_code == 429 or self.status_code >= 500


class BackendClient:
    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        normalized_url = base_url.strip().rstrip("/")
        if not normalized_url.startswith(("http://", "https://")):
            raise ValueError("backend URL must start with http:// or https://")
        if timeout <= 0:
            raise ValueError("backend timeout must be positive")
        self.base_url = normalized_url
        self.timeout = timeout

    def health(self) -> BackendResponse:
        return self._request("GET", "/health")

    def post_message(self, payload: NormalizedMessage) -> BackendResponse:
        return self._request("POST", "/messages", payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> BackendResponse:
        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "tech4city-tdlib-bridge/1",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return BackendResponse(
                    status_code=response.status,
                    body=_decode_json(response.read()),
                )
        except HTTPError as exc:
            return BackendResponse(
                status_code=exc.code,
                body=_decode_json(exc.read()),
            )
        except OSError as exc:
            raise BackendUnavailable("backend request failed") from exc


def _decode_json(raw: bytes) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackendUnavailable("backend returned invalid JSON") from exc
    return parsed if isinstance(parsed, dict) else None


__all__ = ["BackendClient", "BackendResponse", "BackendUnavailable"]
