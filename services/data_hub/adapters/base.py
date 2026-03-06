"""Adapter interface and shared helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.data_hub.exceptions import AdapterNotSupportedError
from services.data_hub.types import NormalizedEnvelope


class IDataSourceAdapter(ABC):
    """Standard adapter interface for all upstream sources."""

    supported_metrics: tuple[str, ...] = ("realtime", "history", "news", "flow")

    def __init__(self, name: str, priority: int, enabled: bool = True) -> None:
        self.name = name
        self.priority = priority
        self.enabled = enabled

    @abstractmethod
    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        """Fetch realtime quote data."""

    @abstractmethod
    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        """Fetch historical series data."""

    @abstractmethod
    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        """Fetch related news items."""

    @abstractmethod
    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        """Fetch fund flow / sector flow data."""

    def health_check(self) -> bool:
        """Basic health check; override for custom checks."""
        return True

    def supports(self, metric: str) -> bool:
        return metric in self.supported_metrics

    def call_metric(self, metric: str, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        """Dispatch metric fetch to concrete methods."""
        if not self.supports(metric):
            raise AdapterNotSupportedError(f"{self.name} does not support {metric}")
        if metric == "realtime":
            if not symbol:
                raise ValueError("symbol is required for realtime metric")
            return self.fetch_realtime(symbol, **kwargs)
        if metric == "history":
            if not symbol:
                raise ValueError("symbol is required for history metric")
            return self.fetch_history(symbol, **kwargs)
        if metric == "news":
            return self.fetch_news(symbol=symbol, **kwargs)
        if metric == "flow":
            return self.fetch_flow(symbol=symbol, **kwargs)
        raise AdapterNotSupportedError(f"unsupported metric {metric}")

