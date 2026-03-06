"""Alpha Vantage adapter for optional global data."""

from __future__ import annotations

import os
from typing import Any

import requests

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import DataSourceError, DataUnavailableError
from services.data_hub.types import NormalizedEnvelope


class AlphaVantageAdapter(IDataSourceAdapter):
    """Optional adapter requiring ALPHA_VANTAGE_API_KEY."""

    def __init__(self, priority: int = 6, enabled: bool = True) -> None:
        super().__init__(name="alpha_vantage", priority=priority, enabled=enabled)
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        self.base_url = "https://www.alphavantage.co/query"
        self.session = requests.Session()

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self._require_key()}
        payload = self._query(params)
        row = payload.get("Global Quote") or {}
        if not row:
            raise DataUnavailableError(f"alpha_vantage realtime empty for {symbol}")
        record = {
            "symbol": row.get("01. symbol"),
            "open": _to_float(row.get("02. open")),
            "high": _to_float(row.get("03. high")),
            "low": _to_float(row.get("04. low")),
            "price": _to_float(row.get("05. price")),
            "volume": _to_float(row.get("06. volume")),
            "latest_trading_day": row.get("07. latest trading day"),
            "change_pct": row.get("10. change percent"),
        }
        return NormalizedEnvelope(
            metric="realtime",
            symbol=symbol,
            source=self.name,
            source_time=record.get("latest_trading_day"),
            records=[record],
            quality_score=0.86,
            metadata={"function": "GLOBAL_QUOTE"},
        )

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        limit = int(kwargs.get("limit", 30))
        params = {"function": "TIME_SERIES_DAILY", "symbol": symbol, "apikey": self._require_key()}
        payload = self._query(params)
        series = payload.get("Time Series (Daily)") or {}
        if not series:
            raise DataUnavailableError(f"alpha_vantage history empty for {symbol}")
        records = []
        for date_key in sorted(series.keys(), reverse=True)[:limit]:
            row = series[date_key]
            records.append(
                {
                    "date": date_key,
                    "open": _to_float(row.get("1. open")),
                    "high": _to_float(row.get("2. high")),
                    "low": _to_float(row.get("3. low")),
                    "close": _to_float(row.get("4. close")),
                    "volume": _to_float(row.get("5. volume")),
                }
            )
        return NormalizedEnvelope(
            metric="history",
            symbol=symbol,
            source=self.name,
            source_time=records[0]["date"],
            records=records,
            quality_score=0.86,
            metadata={"function": "TIME_SERIES_DAILY"},
        )

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        if not symbol:
            raise DataUnavailableError("alpha_vantage news requires symbol")
        limit = int(kwargs.get("limit", 20))
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": symbol,
            "limit": str(limit),
            "apikey": self._require_key(),
        }
        payload = self._query(params)
        rows = payload.get("feed") or []
        if not rows:
            raise DataUnavailableError(f"alpha_vantage news empty for {symbol}")
        records = []
        for item in rows:
            records.append(
                {
                    "title": item.get("title"),
                    "content": item.get("summary"),
                    "time": item.get("time_published"),
                    "source": item.get("source"),
                    "url": item.get("url"),
                    "sentiment": item.get("overall_sentiment_score"),
                }
            )
        return NormalizedEnvelope(
            metric="news",
            symbol=symbol,
            source=self.name,
            source_time=records[0].get("time") if records else None,
            records=records,
            quality_score=0.8,
            metadata={"function": "NEWS_SENTIMENT"},
        )

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("alpha_vantage has no direct A-share flow endpoint")

    def _query(self, params: dict[str, str]) -> dict[str, Any]:
        try:
            resp = self.session.get(self.base_url, params=params, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise DataSourceError(f"alpha_vantage request failed: {exc}") from exc
        if "Note" in payload:
            raise DataUnavailableError(f"alpha_vantage throttled: {payload['Note']}")
        if "Error Message" in payload:
            raise DataUnavailableError(f"alpha_vantage error: {payload['Error Message']}")
        return payload

    def _require_key(self) -> str:
        if not self.api_key:
            raise DataUnavailableError("ALPHA_VANTAGE_API_KEY is not configured")
        return self.api_key


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

