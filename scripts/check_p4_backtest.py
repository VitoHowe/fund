"""P4 validation: strategy signals and backtest runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.backtest import BacktestConfig, BacktestRunner
from services.data_hub import build_default_source_manager
from services.factor_engine import FactorScorer, WeightTemplateManager, build_default_factor_registry
from services.strategy import ScoreMomentumStrategy, ScoreThresholdStrategy


def _result_digest(report: dict) -> dict:
    out: dict = {"snapshot_hash": report.get("snapshot_hash"), "ranking": report.get("ranking"), "strategies": {}}
    for item in report.get("strategies", []):
        out["strategies"][item["strategy"]] = {
            "metrics": item.get("metrics"),
            "trade_count": len(item.get("trades") or []),
            "equity_tail": (item.get("equity_curve") or [])[-3:],
        }
    return out


def main() -> None:
    symbol = "014943"
    proxy_symbol = "159870"
    source_manager = build_default_source_manager()
    registry = build_default_factor_registry()
    weight_manager = WeightTemplateManager(config_path=str(ROOT / "config" / "factor_weights.yaml"))
    scorer = FactorScorer(source_manager=source_manager, registry=registry, weight_manager=weight_manager)
    runner = BacktestRunner(source_manager=source_manager, factor_scorer=scorer)
    strategies = [
        ScoreThresholdStrategy(buy_threshold=60.0, sell_threshold=44.0, min_confidence=0.55),
        ScoreMomentumStrategy(entry_score=56.0, exit_score=42.0, momentum_window=3, min_acceleration=1.2),
    ]
    config = BacktestConfig(initial_capital=100_000.0, fee_rate=0.0003, slippage_bps=2.0, warmup_days=20)
    report_1 = runner.run(
        symbol=symbol,
        strategies=strategies,
        market_state="neutral",
        proxy_symbol=proxy_symbol,
        limit=200,
        config=config,
    )
    report_2 = runner.run(
        symbol=symbol,
        strategies=strategies,
        market_state="neutral",
        proxy_symbol=proxy_symbol,
        limit=200,
        config=config,
    )
    assert len(report_1["strategies"]) >= 2, "at least two strategies are required"
    required_metrics = {"total_return_pct", "max_drawdown_pct", "win_rate", "sharpe", "turnover_ratio"}
    for item in report_1["strategies"]:
        metrics = set((item.get("metrics") or {}).keys())
        missing = required_metrics - metrics
        assert not missing, f"missing metrics: {missing}"
    digest_1 = _result_digest(report_1)
    digest_2 = _result_digest(report_2)
    assert digest_1 == digest_2, "backtest must be reproducible under same snapshot and params"
    output = {
        "symbol": symbol,
        "proxy_symbol": proxy_symbol,
        "checks": {
            "two_strategies_backtest": True,
            "required_kpi_present": True,
            "reproducible_same_input": True,
        },
        "report_digest": digest_1,
        "report": report_1,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

