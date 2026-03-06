"""TDX adapter stub with graceful fallback."""

from __future__ import annotations

from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import DataUnavailableError
from services.data_hub.types import NormalizedEnvelope


class TdxAdapter(IDataSourceAdapter):
    """Placeholder adapter for TDX protocol integration."""

    def __init__(self, priority: int = 4, enabled: bool = True) -> None:
        super().__init__(name="tdx", priority=priority, enabled=enabled)

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("tdx adapter is not wired yet, use eastmoney/akshare fallback")

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("tdx adapter is not wired yet, use eastmoney/efinance fallback")

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("tdx adapter has no news endpoint")

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("tdx adapter flow endpoint is not wired yet")

