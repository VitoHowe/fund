"""Unit tests for backtest runner reproducibility."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from services.backtest import BacktestConfig, BacktestRunner
from services.factor_engine import FactorScorer, WeightTemplateManager, build_default_factor_registry
from services.strategy import ScoreMomentumStrategy, ScoreThresholdStrategy


class FakeSourceManager:
    def fetch_history(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        limit = int(kwargs.get("limit", 200))
        rows = []
        nav = 1.0
        for idx in range(1, 220):
            drift = 0.001 if idx % 12 < 8 else -0.0005
            nav = nav * (1.0 + drift)
            rows.append(
                {
                    "date": f"2026-01-{(idx % 28) + 1:02d}",
                    "unit_nav": round(nav, 6),
                    "daily_change_pct": round(drift * 100.0, 4),
                }
            )
        rows = rows[-limit:]
        return {
            "metric": "history",
            "symbol": symbol,
            "source": "fake",
            "records": list(reversed(rows)),
            "stale": False,
        }


class BacktestRunnerTests(unittest.TestCase):
    def _build_runner(self) -> BacktestRunner:
        registry = build_default_factor_registry()
        root = Path(__file__).resolve().parents[1]
        scorer = FactorScorer(
            source_manager=FakeSourceManager(),
            registry=registry,
            weight_manager=WeightTemplateManager(config_path=str(root / "config" / "factor_weights.yaml")),
        )
        return BacktestRunner(source_manager=FakeSourceManager(), factor_scorer=scorer)

    def test_two_strategies_can_run(self) -> None:
        runner = self._build_runner()
        report = runner.run(
            symbol="014943",
            strategies=[ScoreThresholdStrategy(), ScoreMomentumStrategy()],
            market_state="neutral",
            proxy_symbol="159870",
            limit=120,
            config=BacktestConfig(warmup_days=20),
        )
        self.assertGreaterEqual(len(report["strategies"]), 2)
        for item in report["strategies"]:
            self.assertIn("total_return_pct", item["metrics"])
            self.assertIn("sharpe", item["metrics"])

    def test_same_input_is_reproducible(self) -> None:
        runner = self._build_runner()
        params = dict(
            symbol="014943",
            strategies=[ScoreThresholdStrategy(), ScoreMomentumStrategy()],
            market_state="neutral",
            proxy_symbol="159870",
            limit=120,
            config=BacktestConfig(warmup_days=20),
        )
        report_1 = runner.run(**params)
        report_2 = runner.run(**params)
        self.assertEqual(report_1["snapshot_hash"], report_2["snapshot_hash"])
        m1 = {item["strategy"]: item["metrics"] for item in report_1["strategies"]}
        m2 = {item["strategy"]: item["metrics"] for item in report_2["strategies"]}
        self.assertEqual(m1, m2)


if __name__ == "__main__":
    unittest.main()
