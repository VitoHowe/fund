"""Integration test for source failover and monitor alerts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import DataUnavailableError
from services.data_hub.repository import DataRepository
from services.data_hub.source_manager import SourceManager, SourceManagerConfig
from services.data_hub.types import NormalizedEnvelope
from services.observability import SourceMonitor, SourceMonitorConfig


class _FailingAdapter(IDataSourceAdapter):
    def __init__(self) -> None:
        super().__init__(name="primary_fail", priority=1, enabled=True)

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("forced realtime failure")

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("forced history failure")

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("forced news failure")

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        raise DataUnavailableError("forced flow failure")


class _BackupAdapter(IDataSourceAdapter):
    def __init__(self) -> None:
        super().__init__(name="backup_ok", priority=2, enabled=True)

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        return NormalizedEnvelope(
            metric="realtime",
            symbol=symbol,
            source=self.name,
            source_time="2026-03-06 15:00:00",
            records=[{"symbol": symbol, "name": "test", "unit_nav": 1.02, "daily_change_pct": 0.5}],
            quality_score=0.9,
        )

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        return NormalizedEnvelope(
            metric="history",
            symbol=symbol,
            source=self.name,
            source_time="2026-03-06",
            records=[
                {"date": "2026-03-04", "unit_nav": 1.01, "acc_nav": 1.01, "daily_change_pct": 0.1},
                {"date": "2026-03-05", "unit_nav": 1.02, "acc_nav": 1.02, "daily_change_pct": 0.2},
            ],
            quality_score=0.95,
        )

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        return NormalizedEnvelope(
            metric="news",
            symbol=symbol or "market",
            source=self.name,
            source_time="2026-03-06 14:00:00",
            records=[{"title": "test", "content": "test", "time": "2026-03-06 14:00:00", "source": "unit"}],
            quality_score=0.8,
        )

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        return NormalizedEnvelope(
            metric="flow",
            symbol=symbol or "market",
            source=self.name,
            source_time="2026-03-06 14:00:00",
            records=[{"sector": "化工", "change_pct": 1.0, "main_inflow_ratio": 0.8}],
            quality_score=0.8,
        )


class FailoverIntegrationTests(unittest.TestCase):
    def _build_manager(self) -> SourceManager:
        tmp = tempfile.mkdtemp(prefix="fund-failover-")
        root = Path(__file__).resolve().parents[2]
        repo = DataRepository(
            db_path=str(Path(tmp) / "test.db"),
            schema_path=str(root / "infra" / "db" / "schema.sql"),
        )
        manager = SourceManager(
            adapters=[_FailingAdapter(), _BackupAdapter()],
            config=SourceManagerConfig(failure_threshold=1, cooldown_seconds=30, retry_per_source=0),
            repository=repo,
        )
        return manager

    def test_history_failover_to_backup(self) -> None:
        manager = self._build_manager()
        payload = manager.fetch_history("014943", limit=2, bypass_cache=True)
        self.assertEqual(payload["source"], "backup_ok")
        self.assertGreaterEqual(len(payload.get("records") or []), 1)
        events = manager.get_recent_audit_events(limit=5)
        self.assertTrue(any(item.get("selected_source") == "backup_ok" for item in events))

    def test_monitor_alerts_visible(self) -> None:
        manager = self._build_manager()
        _ = manager.fetch_history("014943", limit=2, bypass_cache=True)
        monitor = SourceMonitor(
            source_manager=manager,
            config=SourceMonitorConfig(max_consecutive_failures_warn=1, max_consecutive_failures_critical=2),
        )
        snap = monitor.snapshot()
        self.assertIn(snap["overall_status"], {"warning", "critical", "healthy"})
        self.assertTrue(len(snap.get("alerts") or []) >= 1)


if __name__ == "__main__":
    unittest.main()
