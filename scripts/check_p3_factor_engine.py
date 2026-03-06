"""P3 validation: factor engine and scoring framework."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.data_hub import build_default_source_manager
from services.factor_engine import FactorScorer, WeightTemplateManager, build_default_factor_registry


def main() -> None:
    symbol = "014943"
    proxy_symbol = "159870"
    manager = build_default_source_manager()
    registry = build_default_factor_registry()
    weight_manager = WeightTemplateManager(config_path=str(ROOT / "config" / "factor_weights.yaml"))
    scorer = FactorScorer(source_manager=manager, registry=registry, weight_manager=weight_manager)

    neutral_card = scorer.score_symbol(symbol=symbol, market_state="neutral", proxy_symbol=proxy_symbol)
    bull_card = scorer.score_symbol(symbol=symbol, market_state="bull", proxy_symbol=proxy_symbol)

    factor_count = len(neutral_card.factor_scores)
    assert factor_count >= 6, f"expected >= 6 factors, got {factor_count}"
    for factor_name, item in neutral_card.factor_scores.items():
        assert 0.0 <= float(item["score"]) <= 100.0, f"factor score out of range: {factor_name}"
        assert item.get("explanation"), f"factor explanation missing: {factor_name}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "factor_weights.yaml"
        shutil.copyfile(ROOT / "config" / "factor_weights.yaml", tmp_path)
        hot_manager = WeightTemplateManager(config_path=str(tmp_path))
        hot_scorer = FactorScorer(source_manager=manager, registry=registry, weight_manager=hot_manager)
        before = hot_scorer.score_symbol(symbol=symbol, market_state="neutral", proxy_symbol=proxy_symbol)
        config_payload = json.loads(tmp_path.read_text(encoding="utf-8"))
        config_payload["templates"]["neutral"]["trend"] = 0.34
        config_payload["templates"]["neutral"]["momentum"] = 0.12
        tmp_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        after = hot_scorer.score_symbol(
            symbol=symbol,
            market_state="neutral",
            proxy_symbol=proxy_symbol,
            force_reload_weights=True,
        )
        assert before.weight_version != after.weight_version, "weight version should change after hot update"

    report = {
        "symbol": symbol,
        "proxy_symbol": proxy_symbol,
        "checks": {
            "factor_count_ge_6": factor_count >= 6,
            "all_factor_explainable": all(
                bool(item.get("explanation")) for item in neutral_card.factor_scores.values()
            ),
            "weight_template_switch_effective": neutral_card.total_score != bull_card.total_score,
            "weight_hot_reload_traceable": True,
            "neutral_weight_version": neutral_card.weight_version,
            "bull_weight_version": bull_card.weight_version,
        },
        "neutral_scorecard": neutral_card.to_dict(),
        "bull_scorecard": bull_card.to_dict(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

