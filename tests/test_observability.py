"""Unit tests for observability monitor."""

from __future__ import annotations

import unittest

from services.observability import SourceMonitor, SourceMonitorConfig


class _FakeSourceManager:
    def get_source_health(self):
        return [
            {
                "source": "eastmoney",
                "enabled": True,
                "failure_count": 3,
                "consecutive_failures": 2,
                "avg_latency_ms": 3200.0,
                "circuit_open_until": "2099-01-01T00:00:00+00:00",
            },
            {
                "source": "akshare",
                "enabled": True,
                "failure_count": 0,
                "consecutive_failures": 0,
                "avg_latency_ms": 120.0,
                "circuit_open_until": None,
            },
        ]


class ObservabilityTests(unittest.TestCase):
    def test_snapshot_and_alerts(self):
        monitor = SourceMonitor(
            source_manager=_FakeSourceManager(),
            config=SourceMonitorConfig(max_consecutive_failures_warn=1, max_consecutive_failures_critical=2),
        )
        snap = monitor.snapshot()
        self.assertIn(snap["overall_status"], {"warning", "critical", "healthy"})
        self.assertGreaterEqual(len(snap.get("alerts") or []), 1)

    def test_prometheus_text(self):
        monitor = SourceMonitor(source_manager=_FakeSourceManager())
        text = monitor.prometheus_text()
        self.assertIn("fund_data_source_enabled", text)
        self.assertIn("fund_data_source_alert_total", text)


if __name__ == "__main__":
    unittest.main()

