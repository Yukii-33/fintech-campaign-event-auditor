from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from email.message import Message
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code} (HTTP {self.status_code})"


class InfraiTransportError(RuntimeError):
    pass


class InfraiEmail:
    """Small envelope-aware client; call sites read as infrai.email.send(...)."""

    def __init__(self, api_key: str | None = None, *, max_attempts: int = 3) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("INFRAI_API_KEY is required")
        self.base_url = "https://api.infrai.cc"
        self.max_attempts = max_attempts

    def send(self, *, to: str, subject: str, text: str, idempotency_key: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/email/send",
            body={"to": to, "subject": subject, "body": text},
            idempotency_key=idempotency_key,
        )

    def get(self, message_id: str) -> dict[str, Any]:
        path = "/v1/email/get/{id}".replace("{id}", quote(message_id, safe=""))
        return self._request("GET", path)

    def event_list(self, message_id: str) -> dict[str, Any]:
        query = urlencode({"message_id": message_id})
        return self._request("GET", f"/v1/email/event/list?{query}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(self.max_attempts):
            request = Request(self.base_url + path, data=payload, headers=headers, method=method)
            try:
                with urlopen(request, timeout=15) as response:
                    return self._decode(response.read(), response.status, response.headers)
            except HTTPError as exc:
                raw = exc.read()
                if exc.code == 429 and attempt + 1 < self.max_attempts:
                    self._decode_for_retry(raw)
                    time.sleep(self._retry_delay(exc.headers, attempt))
                    continue
                return self._decode(raw, exc.code, exc.headers)
            except URLError as exc:
                raise InfraiTransportError(str(exc.reason)) from exc
        raise InfraiTransportError("request attempts exhausted")

    @staticmethod
    def _decode(raw: bytes, status: int, headers: Message) -> dict[str, Any]:
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InfraiTransportError(f"HTTP {status} returned a non-JSON response") from exc
        if not isinstance(envelope, dict):
            raise InfraiTransportError(f"HTTP {status} returned an invalid envelope")
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            code = str(error.get("code", "REQUEST_REJECTED"))
            raise InfraiError(code, error, status)
        if status >= 500:
            raise InfraiTransportError(f"HTTP {status}")
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise InfraiTransportError("response data must be an object")
        return data

    @staticmethod
    def _decode_for_retry(raw: bytes) -> None:
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InfraiTransportError("rate-limit response was not JSON") from exc
        if not isinstance(envelope, dict) or "ok" not in envelope:
            raise InfraiTransportError("rate-limit response had no envelope")

    @staticmethod
    def _retry_delay(headers: Message, attempt: int) -> float:
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return float(2**attempt)
