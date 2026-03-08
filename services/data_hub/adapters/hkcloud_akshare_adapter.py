"""HKCloud akshare-api adapter."""

from __future__ import annotations

import os
from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import AdapterNotSupportedError, DataUnavailableError, DataValidationError
from services.data_hub.http_client import HttpUpstreamClient, UpstreamServiceConfig
from services.data_hub.types import NormalizedEnvelope


class HKCloudAkShareAdapter(IDataSourceAdapter):
    """Remote market-flow adapter backed by HKCloud akshare-api."""

    supported_metrics = ("flow",)

    def __init__(self, priority: int = 3, enabled: bool | None = None) -> None:
        enabled_flag = _env_bool("HKCLOUD_AKSHARE_ENABLED", True) if enabled is None else enabled
        super().__init__(name="hkcloud_akshare", priority=priority, enabled=enabled_flag)
        self.client = HttpUpstreamClient(
            UpstreamServiceConfig(
                name=self.name,
                base_url=os.getenv("HKCLOUD_AKSHARE_URL", "http://189.1.217.66:18082"),
                enabled=enabled_flag,
                timeout_seconds=_env_int("HKCLOUD_AKSHARE_TIMEOUT_SECONDS", 20),
                retry=_env_int("HKCLOUD_AKSHARE_RETRY", 0),
            )
        )

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        raise AdapterNotSupportedError("hkcloud akshare does not provide realtime in fund runtime")

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        raise AdapterNotSupportedError("hkcloud akshare does not provide history in fund runtime")

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise AdapterNotSupportedError("hkcloud akshare does not provide news")

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        if symbol:
            raise AdapterNotSupportedError("hkcloud akshare sector flow only supports market scope")
        indicator = str(kwargs.get("indicator") or "今日")
        payload = self.client.get_json(
            "/api/flow/sector_rank",
            params={"indicator": indicator},
            timeout_seconds=int(kwargs.get("timeout_seconds") or self.client.config.timeout_seconds),
        )
        rows = payload.get("records") or payload.get("items") or payload.get("data") or payload.get("rows") or []
        if not isinstance(rows, list) or not rows:
            raise DataUnavailableError("hkcloud akshare sector flow returned empty")
        records = []
        for item in rows[: int(kwargs.get("limit", 20))]:
            if not isinstance(item, dict):
                continue
            records.append(
                {
                    "sector": item.get("名称") or item.get("sector") or item.get("板块名称"),
                    "change_pct": _to_float(_first(item, f"{indicator}涨跌幅", "涨跌幅", "change_pct")),
                    "main_net_inflow": _to_float(_first(item, f"{indicator}主力净流入-净额", "主力净流入", "main_net_inflow")),
                    "main_inflow_ratio": _to_float(
                        _first(item, f"{indicator}主力净流入-净占比", "主力净流入占比", "main_inflow_ratio")
                    ),
                    "top_stock": _first(item, f"{indicator}主力净流入最大股", "领涨股", "top_stock"),
                }
            )
        records = [row for row in records if row.get("sector")]
        if not records:
            raise DataValidationError("hkcloud akshare sector flow returned unusable rows")
        return NormalizedEnvelope(
            metric="flow",
            symbol="market",
            source=self.name,
            source_time=None,
            records=records,
            quality_score=0.88,
            metadata={"endpoint": "/api/flow/sector_rank", "indicator": indicator, "rows": len(records)},
        )

    def health_check(self) -> bool:
        return bool(self.client.probe_health().get("ok"))


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", "--"):
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default
