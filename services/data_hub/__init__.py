"""Data hub entrypoints and factory."""

import os

from services.data_hub.adapters.akshare_adapter import AkShareAdapter
from services.data_hub.adapters.alpha_vantage_adapter import AlphaVantageAdapter
from services.data_hub.adapters.eastmoney_adapter import EastmoneyAdapter
from services.data_hub.adapters.efinance_adapter import EFinanceAdapter
from services.data_hub.adapters.hkcloud_akshare_adapter import HKCloudAkShareAdapter
from services.data_hub.adapters.hkcloud_efinance_adapter import HKCloudEFinanceAdapter
from services.data_hub.adapters.hkcloud_stock_mcp_adapter import HKCloudStockMcpAdapter
from services.data_hub.adapters.tdx_adapter import TdxAdapter
from services.data_hub.adapters.yfinance_adapter import YFinanceAdapter
from services.data_hub.source_manager import SourceManager, SourceManagerConfig


def build_default_source_manager() -> SourceManager:
    """Build a source manager with the default adapter set."""
    return SourceManager(
        adapters=[
            HKCloudEFinanceAdapter(priority=1),
            HKCloudStockMcpAdapter(priority=2),
            HKCloudAkShareAdapter(priority=3),
            EastmoneyAdapter(priority=4),
            EFinanceAdapter(priority=5),
            AkShareAdapter(priority=6),
            TdxAdapter(priority=7),
            YFinanceAdapter(priority=8),
            AlphaVantageAdapter(priority=9),
        ],
        config=SourceManagerConfig(
            failure_threshold=_env_int("FUND_SOURCE_FAILURE_THRESHOLD", 3),
            cooldown_seconds=_env_int("FUND_SOURCE_COOLDOWN_SECONDS", 90),
            retry_per_source=_env_int("FUND_SOURCE_RETRY_PER_SOURCE", 1),
            timeout_seconds=_env_int("FUND_SOURCE_TIMEOUT_SECONDS", 20),
        ),
    )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default

