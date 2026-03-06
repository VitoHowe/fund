"""Unit tests for factor engine basics."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from services.factor_engine import FactorScorer, WeightTemplateManager, build_default_factor_registry


class FakeSourceManager:
    def fetch_history(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        rows = []
        nav = 1.0
        for day in range(1, 40):
            nav = nav * 1.001
            rows.append(
                {
                    "date": f"2026-02-{day:02d}",
                    "unit_nav": round(nav, 4),
                    "acc_nav": round(nav, 4),
                    "daily_change_pct": 0.1,
                }
            )
        return {
            "metric": "history",
            "symbol": symbol,
            "source": "fake",
            "records": list(reversed(rows)),
            "stale": False,
        }

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return {
            "metric": "flow",
            "symbol": symbol or "market",
            "source": "fake",
            "records": [{"main_inflow_ratio": 1.5}],
            "stale": False,
        }

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return {
            "metric": "news",
            "symbol": symbol or "market",
            "source": "fake",
            "records": [
                {"title": "政策利好", "content": "行业回暖，资金净流入"},
                {"title": "风险提示", "content": "短期波动增加"},
            ],
            "metadata": {"fallback_mode": False},
            "stale": False,
        }


class FactorEngineTests(unittest.TestCase):
    def test_default_registry_has_six_factors(self) -> None:
        registry = build_default_factor_registry()
        self.assertGreaterEqual(len(registry.list()), 6)

    def test_scorecard_contains_explanations(self) -> None:
        registry = build_default_factor_registry()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "weights.yaml"
            config_payload = {
                "version": "test",
                "default_template": "neutral",
                "templates": {
                    "neutral": {
                        "trend": 0.2,
                        "momentum": 0.2,
                        "volatility": 0.2,
                        "drawdown": 0.2,
                        "flow": 0.1,
                        "sentiment": 0.1,
                    }
                },
                "thresholds": {"low_confidence": 0.3},
            }
            config_path.write_text(json.dumps(config_payload), encoding="utf-8")
            scorer = FactorScorer(
                source_manager=FakeSourceManager(),
                registry=registry,
                weight_manager=WeightTemplateManager(config_path=str(config_path)),
            )
            card = scorer.score_symbol(symbol="014943", market_state="neutral")
            self.assertGreaterEqual(len(card.factor_scores), 6)
            for item in card.factor_scores.values():
                self.assertTrue(item.get("explanation"))
                self.assertGreaterEqual(float(item["score"]), 0.0)
                self.assertLessEqual(float(item["score"]), 100.0)


if __name__ == "__main__":
    unittest.main()

