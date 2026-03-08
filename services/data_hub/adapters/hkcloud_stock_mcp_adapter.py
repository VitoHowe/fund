"""HKCloud stock-data-mcp adapter."""

from __future__ import annotations

import csv
import os
from io import StringIO
from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import DataUnavailableError, DataValidationError
from services.data_hub.stock_mcp_client import StockMcpClient
from services.data_hub.types import NormalizedEnvelope


class HKCloudStockMcpAdapter(IDataSourceAdapter):
    """News and ETF flow adapter backed by stock-data-mcp."""

    supported_metrics = ("news", "flow")

    def __init__(self, priority: int = 2, enabled: bool | None = None) -> None:
        enabled_flag = _env_bool("HKCLOUD_STOCK_MCP_ENABLED", True) if enabled is None else enabled
        super().__init__(name="hkcloud_stock_mcp", priority=priority, enabled=enabled_flag)
        self.client = StockMcpClient(
            os.getenv("HKCLOUD_STOCK_MCP_URL", "http://189.1.217.66:18808/mcp"),
            enabled=enabled_flag,
            timeout_seconds=_env_int("HKCLOUD_STOCK_MCP_TIMEOUT_SECONDS", 25),
        )

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("stock-data-mcp does not provide fund realtime in this runtime")

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("stock-data-mcp does not provide fund history in this runtime")

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        limit = int(kwargs.get("limit", 20))
        fallback_mode = False
        if symbol:
            result = self.client.call_tool("stock_news", {"symbol": symbol, "limit": limit})
            text = _extract_text(result)
            records = _parse_symbol_news(text, symbol=symbol, limit=limit)
            if not records:
                fallback_mode = True
                result = self.client.call_tool("stock_news_global", {})
                text = _extract_text(result)
                records = _parse_global_news(text, limit=limit)
        else:
            result = self.client.call_tool("stock_news_global", {})
            text = _extract_text(result)
            records = _parse_global_news(text, limit=limit)
        if not records:
            raise DataUnavailableError(f"stock-data-mcp news returned empty for {symbol or 'market'}")
        source_time = next((row.get("time") for row in records if row.get("time")), None)
        return NormalizedEnvelope(
            metric="news",
            symbol=symbol or "market",
            source=self.name,
            source_time=source_time,
            records=records,
            quality_score=0.86 if not fallback_mode else 0.72,
            metadata={
                "tool": "stock_news" if symbol else "stock_news_global",
                "fallback_mode": fallback_mode,
                "rows": len(records),
            },
        )

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        limit = int(kwargs.get("limit", 20))
        if symbol:
            result = self.client.call_tool("stock_fund_flow", {"symbol": symbol})
            text = _extract_text(result)
            if _looks_like_failure_text(text):
                raise DataUnavailableError(text or f"stock-data-mcp fund flow unavailable for {symbol}")
            records = _parse_stock_flow(text, limit=limit)
        else:
            result = self.client.call_tool(
                "stock_sector_fund_flow_rank",
                {
                    "cate": str(kwargs.get("sector_type") or "行业资金流"),
                    "days": str(kwargs.get("indicator") or "今日"),
                },
            )
            text = _extract_text(result)
            if _looks_like_failure_text(text):
                raise DataUnavailableError(text or "stock-data-mcp sector flow unavailable")
            records = _parse_sector_flow(text, limit=limit)
        if not records:
            raise DataValidationError("stock-data-mcp flow returned no usable rows")
        source_time = next((row.get("date") for row in reversed(records) if row.get("date")), None)
        return NormalizedEnvelope(
            metric="flow",
            symbol=symbol or "market",
            source=self.name,
            source_time=source_time,
            records=records,
            quality_score=0.82,
            metadata={"rows": len(records), "tool": "stock_fund_flow" if symbol else "stock_sector_fund_flow_rank"},
        )

    def health_check(self) -> bool:
        return bool(self.client.probe_health().get("ok"))


def _extract_text(result: dict[str, Any]) -> str:
    content = result.get("content") or []
    out: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and item.get("text"):
            out.append(str(item["text"]))
    return "\n".join(out).strip()


def _parse_symbol_news(text: str, *, symbol: str, limit: int) -> list[dict[str, Any]]:
    lines = _body_lines(text)
    records: list[dict[str, Any]] = []
    for line in lines:
        if "," not in line:
            continue
        timestamp, content = line.split(",", 1)
        if timestamp.strip() == "时间" and content.strip() == "内容":
            continue
        content = content.strip()
        if not content:
            continue
        records.append(
            {
                "title": content[:80],
                "content": content,
                "time": timestamp.strip(),
                "source": "stock-data-mcp",
                "url": None,
                "relevance": 1.0 if symbol in content else 0.5,
            }
        )
        if len(records) >= limit:
            break
    return records


def _parse_global_news(text: str, *, limit: int) -> list[dict[str, Any]]:
    lines = _body_lines(text)
    records: list[dict[str, Any]] = []
    for line in lines:
        if "," not in line:
            continue
        head, source = line.rsplit(",", 1)
        if "," in head:
            timestamp, content = head.split(",", 1)
        else:
            timestamp, content = "", head
        if timestamp.strip() == "时间" and content.strip() == "内容" and source.strip() == "来源":
            continue
        content = content.strip()
        if not content:
            continue
        records.append(
            {
                "title": content[:80],
                "content": content,
                "time": timestamp.strip() or None,
                "source": source.strip() or "stock-data-mcp",
                "url": None,
                "relevance": 0.2,
            }
        )
        if len(records) >= limit:
            break
    return records


def _parse_stock_flow(text: str, *, limit: int) -> list[dict[str, Any]]:
    rows = _parse_csv_rows(text)
    output: list[dict[str, Any]] = []
    for row in rows[-limit:]:
        output.append(
            {
                "symbol": row.get("股票代码"),
                "name": row.get("股票名称"),
                "latest_price": _to_float(row.get("收盘价")),
                "change_pct": _to_float(row.get("涨跌幅")),
                "main_net_inflow": _to_float(row.get("主力净流入")),
                "main_inflow_ratio": _to_float(row.get("主力净流入占比")),
                "date": row.get("日期"),
            }
        )
    return output


def _parse_sector_flow(text: str, *, limit: int) -> list[dict[str, Any]]:
    rows = _parse_csv_rows(text)
    output: list[dict[str, Any]] = []
    for row in rows[:limit]:
        output.append(
            {
                "sector": row.get("名称") or row.get("板块名称") or row.get("sector"),
                "change_pct": _to_float(row.get("今日涨跌幅") or row.get("涨跌幅")),
                "main_net_inflow": _to_float(row.get("今日主力净流入-净额") or row.get("主力净流入")),
                "main_inflow_ratio": _to_float(row.get("今日主力净流入-净占比") or row.get("主力净流入占比")),
                "top_stock": row.get("今日主力净流入最大股") or row.get("领涨股"),
            }
        )
    return [row for row in output if row.get("sector")]


def _parse_csv_rows(text: str) -> list[dict[str, str]]:
    lines = [line for line in _body_lines(text) if "," in line]
    if len(lines) < 2:
        return []
    reader = csv.DictReader(StringIO("\n".join(lines)))
    return [
        {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
        for row in reader
    ]


def _body_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _looks_like_failure_text(text: str) -> bool:
    lowered = text.lower()
    return "not found" in lowered or ("失败" in text and "数据来源" not in text)


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    text = str(value).replace("%", "").replace(",", "").strip()
    try:
        return float(text)
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
