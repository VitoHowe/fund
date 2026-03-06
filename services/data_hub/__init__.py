"""Data hub entrypoints and factory."""

from services.data_hub.adapters.akshare_adapter import AkShareAdapter
from services.data_hub.adapters.alpha_vantage_adapter import AlphaVantageAdapter
from services.data_hub.adapters.eastmoney_adapter import EastmoneyAdapter
from services.data_hub.adapters.efinance_adapter import EFinanceAdapter
from services.data_hub.adapters.tdx_adapter import TdxAdapter
from services.data_hub.adapters.yfinance_adapter import YFinanceAdapter
from services.data_hub.source_manager import SourceManager


def build_default_source_manager() -> SourceManager:
    """Build a source manager with the default adapter set."""
    return SourceManager(
        adapters=[
            EastmoneyAdapter(priority=1),
            EFinanceAdapter(priority=2),
            AkShareAdapter(priority=3),
            TdxAdapter(priority=4),
            YFinanceAdapter(priority=5),
            AlphaVantageAdapter(priority=6),
        ]
    )

