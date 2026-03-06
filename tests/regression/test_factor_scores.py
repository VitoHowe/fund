"""Regression test for factor score stability on fixed dataset."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from typing import Any

from services.factor_engine import FactorScorer, WeightTemplateManager, build_default_factor_registry


class _FixtureSourceManager:
    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = fixture

    def fetch_history(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        limit = int(kwargs.get("limit", len(self.fixture["history_records"])))
        rows = self.fixture["history_records"][-limit:]
        return {
            "metric": "history",
            "symbol": symbol,
            "source": "fixture",
            "records": list(reversed(rows)),
            "stale": False,
        }

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return {
            "metric": "flow",
            "symbol": symbol or self.fixture.get("proxy_symbol"),
            "source": "fixture",
            "records": [dict(self.fixture["flow_record"])],
            "stale": False,
        }

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return {"metric": "news", "symbol": symbol or "market", "source": "fixture", "records": [], "stale": False}


class FactorRegressionTests(unittest.TestCase):
    def test_fixed_snapshot_score_hash(self) -> None:
        root = Path(__file__).resolve().parents[2]
        fixture_path = root / "tests" / "fixtures" / "factor_regression_014943.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        source_manager = _FixtureSourceManager(fixture)
        scorer = FactorScorer(
            source_manager=source_manager,
            registry=build_default_factor_registry(),
            weight_manager=WeightTemplateManager(config_path=str(root / "config" / "factor_weights.yaml")),
        )
        card = scorer.score_symbol(
            symbol=fixture["symbol"],
            market_state="neutral",
            proxy_symbol=fixture.get("proxy_symbol"),
            extra_context={"news_feature": fixture["news_feature"]},
        ).to_dict()
        stable_payload = {
            "total_score": card["total_score"],
            "confidence": card["confidence"],
            "risk_tags": card["risk_tags"],
            "factor_scores": {
                key: {
                    "score": value.get("score"),
                    "confidence": value.get("confidence"),
                    "risk_tags": value.get("risk_tags"),
                    "source_refs": value.get("source_refs"),
                }
                for key, value in sorted((card.get("factor_scores") or {}).items())
            },
        }
        digest = hashlib.sha256(
            json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        expected = fixture.get("expected_score_hash")
        if expected == "TO_BE_FILLED":
            self.skipTest(f"baseline hash not initialized, current hash={digest}")
        self.assertEqual(digest, expected)


if __name__ == "__main__":
    unittest.main()

