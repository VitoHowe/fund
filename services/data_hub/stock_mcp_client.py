"""Minimal HTTP MCP client for the stock-data-mcp upstream."""

from __future__ import annotations

import json
import threading
from itertools import count
from typing import Any

import requests

from services.data_hub.exceptions import (
    DataProtocolError,
    DataSourceError,
    DataTimeoutError,
    DataTransportError,
    DataUnavailableError,
)


class StockMcpClient:
    """Call MCP tools over streamable HTTP."""

    def __init__(self, base_url: str, *, enabled: bool = True, timeout_seconds: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self._lock = threading.RLock()
        self._session_id: str | None = None
        self._rpc_ids = count(1)

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise DataUnavailableError("stock-data-mcp is disabled")
        with self._lock:
            self._ensure_session(timeout_seconds=timeout_seconds)
            payload = {
                "jsonrpc": "2.0",
                "id": next(self._rpc_ids),
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": arguments or {},
                },
            }
            response = self._post(payload, timeout_seconds=timeout_seconds)
            messages = self._parse_rpc_messages(response)
            if not messages:
                raise DataProtocolError(f"stock-data-mcp returned empty response for tool={name}")
            message = messages[-1]
            error = message.get("error")
            if error:
                raise DataSourceError(f"stock-data-mcp tool {name} failed: {error.get('message') or error}")
            result = message.get("result") or {}
            if not isinstance(result, dict):
                raise DataProtocolError(f"stock-data-mcp tool {name} returned invalid result")
            return result

    def probe_health(self) -> dict[str, Any]:
        try:
            result = self.call_tool("data_source_status", {})
            return {"ok": True, "message": self._extract_text(result)[:200]}
        except DataSourceError as exc:
            return {"ok": False, "message": str(exc)}

    @staticmethod
    def _extract_text(result: dict[str, Any]) -> str:
        content = result.get("content") or []
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()

    def _ensure_session(self, *, timeout_seconds: int | None = None) -> None:
        if self._session_id:
            return
        init_payload = {
            "jsonrpc": "2.0",
            "id": next(self._rpc_ids),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "fund-intel", "version": "0.1"},
            },
        }
        response = self._post(init_payload, timeout_seconds=timeout_seconds)
        session_id = response.headers.get("mcp-session-id")
        if not session_id:
            raise DataProtocolError("stock-data-mcp did not return mcp-session-id")
        self._session_id = session_id
        self._post(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            timeout_seconds=timeout_seconds,
        )

    def _post(self, payload: dict[str, Any], *, timeout_seconds: int | None = None) -> requests.Response:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        try:
            response = self.session.post(
                self.base_url,
                json=payload,
                headers=headers,
                timeout=int(timeout_seconds or self.timeout_seconds),
            )
        except requests.Timeout as exc:
            raise DataTimeoutError("stock-data-mcp request timed out") from exc
        except requests.ConnectionError as exc:
            raise DataTransportError(f"stock-data-mcp transport error: {exc}") from exc
        except requests.RequestException as exc:
            raise DataTransportError(f"stock-data-mcp request error: {exc}") from exc
        if response.status_code >= 400:
            raise DataSourceError(f"stock-data-mcp http {response.status_code}: {response.text[:300]}")
        return response

    def _parse_rpc_messages(self, response: requests.Response) -> list[dict[str, Any]]:
        content_type = response.headers.get("content-type") or ""
        if content_type.startswith("application/json"):
            try:
                payload = response.json()
            except ValueError as exc:
                raise DataProtocolError("stock-data-mcp returned invalid json") from exc
            if isinstance(payload, dict):
                return [payload]
            raise DataProtocolError("stock-data-mcp returned unexpected json response")
        raw_text = response.content.decode("utf-8", "replace")
        messages: list[dict[str, Any]] = []
        current: list[str] = []
        for line in raw_text.splitlines():
            if line.startswith("data: "):
                current.append(line[6:])
                continue
            if line.strip():
                continue
            if not current:
                continue
            messages.append(self._load_message("".join(current)))
            current = []
        if current:
            messages.append(self._load_message("".join(current)))
        return messages

    @staticmethod
    def _load_message(blob: str) -> dict[str, Any]:
        try:
            payload = json.loads(blob)
        except ValueError as exc:
            raise DataProtocolError("stock-data-mcp returned malformed SSE payload") from exc
        if not isinstance(payload, dict):
            raise DataProtocolError("stock-data-mcp SSE payload is not an object")
        return payload
