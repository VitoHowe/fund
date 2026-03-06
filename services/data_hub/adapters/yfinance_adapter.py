"""yfinance adapter for global market backup."""

from __future__ import annotations

from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import DataSourceError, DataUnavailableError
from services.data_hub.types import NormalizedEnvelope

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None


class YFinanceAdapter(IDataSourceAdapter):
    """Backup adapter for global ticker data."""

    def __init__(self, priority: int = 5, enabled: bool = True) -> None:
        super().__init__(name="yfinance", priority=priority, enabled=enabled)

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        ticker = _to_ticker(symbol)
        t = _ensure_ticker(ticker)
        try:
            hist = t.history(period="2d", interval="1d")
        except Exception as exc:
            raise DataSourceError(f"yfinance realtime failed: {exc}") from exc
        if hist is None or hist.empty:
            raise DataUnavailableError(f"yfinance realtime empty for {ticker}")
        last = hist.iloc[-1]
        record = {
            "symbol": ticker,
            "close": _to_float(last.get("Close")),
            "open": _to_float(last.get("Open")),
            "high": _to_float(last.get("High")),
            "low": _to_float(last.get("Low")),
            "volume": _to_float(last.get("Volume")),
            "date": str(hist.index[-1].date()),
        }
        return NormalizedEnvelope(
            metric="realtime",
            symbol=symbol,
            source=self.name,
            source_time=record["date"],
            records=[record],
            quality_score=0.8,
            metadata={"ticker": ticker},
        )

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        ticker = _to_ticker(symbol)
        t = _ensure_ticker(ticker)
        period = kwargs.get("period", "6mo")
        interval = kwargs.get("interval", "1d")
        limit = int(kwargs.get("limit", 30))
        try:
            hist = t.history(period=period, interval=interval)
        except Exception as exc:
            raise DataSourceError(f"yfinance history failed: {exc}") from exc
        if hist is None or hist.empty:
            raise DataUnavailableError(f"yfinance history empty for {ticker}")
        records = []
        for idx, row in hist.tail(limit).iterrows():
            records.append(
                {
                    "date": str(idx.date()),
                    "open": _to_float(row.get("Open")),
                    "high": _to_float(row.get("High")),
                    "low": _to_float(row.get("Low")),
                    "close": _to_float(row.get("Close")),
                    "volume": _to_float(row.get("Volume")),
                }
            )
        records.reverse()
        return NormalizedEnvelope(
            metric="history",
            symbol=symbol,
            source=self.name,
            source_time=records[0]["date"],
            records=records,
            quality_score=0.8,
            metadata={"ticker": ticker, "period": period, "interval": interval},
        )

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        if not symbol:
            raise DataUnavailableError("yfinance news requires symbol")
        ticker = _to_ticker(symbol)
        t = _ensure_ticker(ticker)
        try:
            news = t.news or []
        except Exception as exc:
            raise DataSourceError(f"yfinance news failed: {exc}") from exc
        if not news:
            raise DataUnavailableError(f"yfinance news empty for {ticker}")
        limit = int(kwargs.get("limit", 20))
        records = []
        for item in news[:limit]:
            records.append(
                {
                    "title": item.get("title"),
                    "content": item.get("summary"),
                    "time": item.get("providerPublishTime"),
                    "source": item.get("publisher"),
                    "url": item.get("link"),
                }
            )
        return NormalizedEnvelope(
            metric="news",
            symbol=symbol,
            source=self.name,
            source_time=str(records[0].get("time")) if records else None,
            records=records,
            quality_score=0.72,
            metadata={"ticker": ticker},
        )

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("yfinance does not expose A-share flow style endpoints")


def _ensure_ticker(ticker: str):
    if yf is None:
        raise DataSourceError("yfinance is not installed")
    return yf.Ticker(ticker)


def _to_ticker(symbol: str) -> str:
    if "." in symbol:
        return symbol
    if len(symbol) == 6 and symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SS"
    if len(symbol) == 6 and symbol.startswith(("0", "1", "2", "3")):
        return f"{symbol}.SZ"
    return symbol


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

