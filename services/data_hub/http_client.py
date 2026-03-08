"""Shared HTTP client for remote upstream services."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests

from services.data_hub.exceptions import (
    DataProtocolError,
    DataSourceError,
    DataTimeoutError,
    DataTransportError,
    DataUnavailableError,
    DataUpstreamError,
)


@dataclass(slots=True)
class UpstreamServiceConfig:
    """Runtime config for one remote upstream service."""

    name: str
    base_url: str
    enabled: bool = True
    timeout_seconds: int = 15
    retry: int = 0
    health_path: str = "/health"


class HttpUpstreamClient:
    """Small resilient JSON client with error classification."""

    def __init__(self, config: UpstreamServiceConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._request(
            "GET",
            path=path,
            params=params,
            timeout_seconds=timeout_seconds,
            headers=headers,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise DataProtocolError(f"{self.config.name} returned non-json payload for {path}") from exc
        if not isinstance(payload, dict):
            raise DataProtocolError(f"{self.config.name} returned non-object json for {path}")
        return payload

    def get_text(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        response = self._request(
            "GET",
            path=path,
            params=params,
            timeout_seconds=timeout_seconds,
            headers=headers,
        )
        return response.text

    def probe_health(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {"ok": False, "status_code": None, "message": "disabled"}
        try:
            response = self._request("GET", path=self.config.health_path, timeout_seconds=min(self.config.timeout_seconds, 8))
            return {
                "ok": response.status_code == 200,
                "status_code": response.status_code,
                "message": response.text[:200],
            }
        except DataSourceError as exc:
            return {"ok": False, "status_code": None, "message": str(exc)}

    def _request(
        self,
        method: str,
        *,
        path: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        if not self.config.enabled:
            raise DataUnavailableError(f"{self.config.name} is disabled")
        url = urljoin(self.config.base_url.rstrip("/") + "/", path.lstrip("/"))
        timeout = int(timeout_seconds or self.config.timeout_seconds)
        last_error: Exception | None = None
        for attempt in range(self.config.retry + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=timeout,
                    headers=headers,
                )
                if response.status_code == 404:
                    raise DataUnavailableError(f"{self.config.name} endpoint not found: {path}")
                if response.status_code >= 500:
                    text = response.text[:300].strip()
                    raise DataUpstreamError(
                        f"{self.config.name} upstream {response.status_code} for {path}: {text or 'server error'}"
                    )
                if response.status_code >= 400:
                    text = response.text[:300].strip()
                    raise DataSourceError(
                        f"{self.config.name} upstream {response.status_code} for {path}: {text or 'request failed'}"
                    )
                return response
            except requests.Timeout as exc:
                last_error = DataTimeoutError(f"{self.config.name} timeout for {path}")  # type: ignore[assignment]
            except requests.ConnectionError as exc:
                last_error = DataTransportError(f"{self.config.name} transport error for {path}: {exc}")  # type: ignore[assignment]
            except requests.RequestException as exc:
                last_error = DataTransportError(f"{self.config.name} request error for {path}: {exc}")  # type: ignore[assignment]
            except DataSourceError as exc:
                last_error = exc
                if not isinstance(exc, (DataTimeoutError, DataTransportError)):
                    raise
            if attempt >= self.config.retry:
                break
            time.sleep(min(1.0, 0.25 * (attempt + 1)))
        if isinstance(last_error, Exception):
            raise last_error
        raise DataTransportError(f"{self.config.name} request failed for {path}")
