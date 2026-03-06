"""efinance adapter."""

from __future__ import annotations

from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import DataSourceError, DataUnavailableError
from services.data_hub.types import NormalizedEnvelope

try:
    import efinance as ef
except Exception:  # pragma: no cover
    ef = None


class EFinanceAdapter(IDataSourceAdapter):
    """Adapter backed by the efinance package."""

    def __init__(self, priority: int = 2, enabled: bool = True) -> None:
        super().__init__(name="efinance", priority=priority, enabled=enabled)

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        _ensure_efinance_available()
        try:
            df = ef.fund.get_realtime_increase_rate(symbol)
        except Exception as exc:
            raise DataSourceError(f"efinance realtime failed: {exc}") from exc
        if df is None or df.empty:
            raise DataUnavailableError(f"efinance realtime returned empty for {symbol}")
        row = df.iloc[0].to_dict()
        record = {
            "symbol": row.get("基金代码") or symbol,
            "name": row.get("基金名称"),
            "unit_nav": _to_float(row.get("最新净值")),
            "daily_change_pct": _to_float(row.get("估算涨跌幅")),
            "nav_date": row.get("最新净值公开日期"),
            "trade_time": row.get("估算时间"),
        }
        return NormalizedEnvelope(
            metric="realtime",
            symbol=symbol,
            source=self.name,
            source_time=record.get("trade_time") or record.get("nav_date"),
            records=[record],
            quality_score=0.9 if record.get("daily_change_pct") is not None else 0.82,
            metadata={"method": "ef.fund.get_realtime_increase_rate"},
        )

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        _ensure_efinance_available()
        limit = int(kwargs.get("limit", 30))
        try:
            df = ef.fund.get_quote_history(symbol)
        except Exception as exc:
            raise DataSourceError(f"efinance history failed: {exc}") from exc
        if df is None or df.empty:
            raise DataUnavailableError(f"efinance history returned empty for {symbol}")
        records = []
        for _, row in df.head(limit).iterrows():
            item = row.to_dict()
            records.append(
                {
                    "date": item.get("日期"),
                    "unit_nav": _to_float(item.get("单位净值")),
                    "acc_nav": _to_float(item.get("累计净值")),
                    "daily_change_pct": _to_float(item.get("涨跌幅")),
                }
            )
        return NormalizedEnvelope(
            metric="history",
            symbol=symbol,
            source=self.name,
            source_time=records[0].get("date"),
            records=records,
            quality_score=0.94,
            metadata={"method": "ef.fund.get_quote_history", "rows": len(records)},
        )

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("efinance adapter does not provide a stable news endpoint")

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("efinance adapter does not provide a stable flow endpoint")


def _ensure_efinance_available() -> None:
    if ef is None:
        raise DataSourceError("efinance is not installed")


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

