"""HKCloud efinance-api adapter."""

from __future__ import annotations

import os
from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import AdapterNotSupportedError, DataUnavailableError, DataValidationError
from services.data_hub.http_client import HttpUpstreamClient, UpstreamServiceConfig
from services.data_hub.types import NormalizedEnvelope


class HKCloudEFinanceAdapter(IDataSourceAdapter):
    """Remote fund data adapter backed by HKCloud efinance-api."""

    supported_metrics = ("realtime", "history")

    def __init__(self, priority: int = 1, enabled: bool | None = None) -> None:
        enabled_flag = _env_bool("HKCLOUD_EFINANCE_ENABLED", True) if enabled is None else enabled
        super().__init__(name="hkcloud_efinance", priority=priority, enabled=enabled_flag)
        self.client = HttpUpstreamClient(
            UpstreamServiceConfig(
                name=self.name,
                base_url=os.getenv("HKCLOUD_EFINANCE_URL", "http://189.1.217.66:18081"),
                enabled=enabled_flag,
                timeout_seconds=_env_int("HKCLOUD_EFINANCE_TIMEOUT_SECONDS", 20),
                retry=_env_int("HKCLOUD_EFINANCE_RETRY", 0),
            )
        )

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        payload = self.client.get_json(
            "/api/fund/realtime",
            params={"code": symbol},
            timeout_seconds=int(kwargs.get("timeout_seconds") or self.client.config.timeout_seconds),
        )
        row = _pick_row(payload, symbol=symbol)
        if not row:
            raise DataUnavailableError(f"hkcloud efinance realtime returned empty for {symbol}")
        record = {
            "symbol": row.get("基金代码") or row.get("股票代码") or row.get("code") or symbol,
            "name": row.get("基金名称") or row.get("股票名称") or row.get("name"),
            "unit_nav": _to_float(_first(row, "最新净值", "单位净值", "最新价", "净值", "收盘")),
            "daily_change_pct": _to_float(_first(row, "估算涨跌幅", "涨跌幅", "日增长率")),
            "estimated_nav": _to_float(_first(row, "估算净值", "GSZ", "估算值")),
            "estimated_change_pct": _to_float(_first(row, "估算涨跌幅", "GSZZL")),
            "trade_time": _first(row, "估值时间", "trade_time", "时间"),
            "nav_date": _first(row, "净值日期", "日期", "nav_date"),
        }
        if record["unit_nav"] is None:
            raise DataValidationError(f"hkcloud efinance realtime missing nav field for {symbol}")
        return NormalizedEnvelope(
            metric="realtime",
            symbol=symbol,
            source=self.name,
            source_time=record.get("trade_time") or record.get("nav_date"),
            records=[record],
            quality_score=0.9 if record.get("estimated_nav") is not None else 0.82,
            metadata={"endpoint": "/api/fund/realtime"},
        )

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        limit = int(kwargs.get("limit", 30))
        payload = self.client.get_json(
            "/api/fund/history",
            params={"code": symbol, "limit": limit},
            timeout_seconds=int(kwargs.get("timeout_seconds") or self.client.config.timeout_seconds),
        )
        rows = payload.get("records") or payload.get("items") or payload.get("data") or []
        if not isinstance(rows, list) or not rows:
            raise DataUnavailableError(f"hkcloud efinance history returned empty for {symbol}")
        records = []
        for item in rows[:limit]:
            if not isinstance(item, dict):
                continue
            records.append(
                {
                    "date": _first(item, "日期", "date"),
                    "unit_nav": _to_float(_first(item, "单位净值", "DWJZ", "收盘", "最新净值")),
                    "acc_nav": _to_float(_first(item, "累计净值", "LJJZ", "收盘")),
                    "daily_change_pct": _to_float(_first(item, "涨跌幅", "JZZZL", "日增长率")),
                    "sub_status": _first(item, "申购状态", "SGZT"),
                    "red_status": _first(item, "赎回状态", "SHZT"),
                }
            )
        records = [row for row in records if row.get("date") and row.get("unit_nav") is not None]
        if not records:
            raise DataValidationError(f"hkcloud efinance history had no usable rows for {symbol}")
        if len(records) < _min_history_rows(limit):
            raise DataValidationError(
                f"hkcloud efinance history insufficient rows for {symbol}: {len(records)}"
            )
        return NormalizedEnvelope(
            metric="history",
            symbol=symbol,
            source=self.name,
            source_time=str(records[0].get("date")),
            records=records,
            quality_score=0.9,
            metadata={"endpoint": "/api/fund/history", "rows": len(records)},
        )

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise AdapterNotSupportedError("hkcloud efinance does not provide news")

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise AdapterNotSupportedError("hkcloud efinance does not provide flow")

    def health_check(self) -> bool:
        return bool(self.client.probe_health().get("ok"))


def _pick_row(payload: dict[str, Any], *, symbol: str) -> dict[str, Any] | None:
    rows = payload.get("records") or payload.get("items") or payload.get("data") or []
    if isinstance(rows, dict):
        return rows
    if not isinstance(rows, list) or not rows:
        return None
    for item in rows:
        if not isinstance(item, dict):
            continue
        code = str(item.get("基金代码") or item.get("股票代码") or item.get("code") or "")
        if code == symbol:
            return item
    return next((item for item in rows if isinstance(item, dict)), None)


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


def _min_history_rows(limit: int) -> int:
    if limit <= 2:
        return 2
    if limit <= 10:
        return min(limit, 3)
    return min(limit, 5)


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
