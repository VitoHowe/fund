"""Backtest runner with snapshot-based reproducibility."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from services.backtest.metrics import compute_kpis
from services.factor_engine.scoring import FactorScorer
from services.strategy.base_strategy import IStrategy


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class BacktestConfig:
    initial_capital: float = 100_000.0
    fee_rate: float = 0.0003
    slippage_bps: float = 2.0
    warmup_days: int = 20


@dataclass(slots=True)
class BacktestResult:
    strategy: str
    symbol: str
    market_state: str
    snapshot_hash: str
    config: dict[str, Any]
    metrics: dict[str, float]
    equity_curve: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    score_series: list[dict[str, Any]]
    generated_at: str = field(default_factory=now_utc_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BacktestRunner:
    """Run strategy backtests from a fixed historical snapshot."""

    def __init__(self, source_manager: Any, factor_scorer: FactorScorer) -> None:
        self.source_manager = source_manager
        self.factor_scorer = factor_scorer

    def run(
        self,
        symbol: str,
        strategies: list[IStrategy],
        market_state: str = "neutral",
        proxy_symbol: str | None = None,
        limit: int = 240,
        history_rows: list[dict[str, Any]] | None = None,
        config: BacktestConfig | None = None,
    ) -> dict[str, Any]:
        cfg = config or BacktestConfig()
        history_rows = list(history_rows) if history_rows is not None else self.load_history_snapshot(symbol=symbol, limit=limit)
        if len(history_rows) < 8:
            raise ValueError("history snapshot is not enough for backtest")
        effective_warmup_days = min(cfg.warmup_days, max(5, len(history_rows) - 3))
        snapshot_hash = self._hash_snapshot(history_rows)
        score_series = self._build_score_series(
            symbol=symbol,
            history_rows=history_rows,
            market_state=market_state,
            proxy_symbol=proxy_symbol,
            warmup_days=effective_warmup_days,
        )
        results: list[BacktestResult] = []
        for strategy in strategies:
            result = self._simulate(
                symbol=symbol,
                strategy=strategy,
                market_state=market_state,
                score_series=score_series,
                history_rows=history_rows,
                snapshot_hash=snapshot_hash,
                config=cfg,
                effective_warmup_days=effective_warmup_days,
            )
            results.append(result)
        ranking = sorted(
            [
                {
                    "strategy": item.strategy,
                    "total_return_pct": item.metrics.get("total_return_pct", 0.0),
                    "max_drawdown_pct": item.metrics.get("max_drawdown_pct", 0.0),
                    "sharpe": item.metrics.get("sharpe", 0.0),
                }
                for item in results
            ],
            key=lambda row: (row["total_return_pct"], row["sharpe"]),
            reverse=True,
        )
        return {
            "symbol": symbol,
            "market_state": market_state,
            "snapshot_hash": snapshot_hash,
            "history_rows": len(history_rows),
            "strategies": [item.to_dict() for item in results],
            "ranking": ranking,
        }

    def load_history_snapshot(self, symbol: str, limit: int, *, bypass_cache: bool = False) -> list[dict[str, Any]]:
        return self._load_history_snapshot(symbol=symbol, limit=limit, bypass_cache=bypass_cache)

    def _load_history_snapshot(self, symbol: str, limit: int, *, bypass_cache: bool = False) -> list[dict[str, Any]]:
        payload = self.source_manager.fetch_history(symbol, limit=limit, bypass_cache=bypass_cache)
        rows = payload.get("records") or []
        cleaned: list[dict[str, Any]] = []
        for row in rows:
            date = row.get("date")
            nav = _to_float(row.get("unit_nav"))
            if not date or nav is None:
                continue
            cleaned.append(
                {
                    "date": str(date),
                    "unit_nav": nav,
                    "daily_change_pct": _to_float(row.get("daily_change_pct")),
                }
            )
        cleaned.sort(key=lambda item: item["date"])
        if len(cleaned) > limit:
            cleaned = cleaned[-limit:]
        return cleaned

    def _build_score_series(
        self,
        symbol: str,
        history_rows: list[dict[str, Any]],
        market_state: str,
        proxy_symbol: str | None,
        warmup_days: int,
    ) -> list[dict[str, Any]]:
        snapshot_manager = _SnapshotSourceManager(history_rows=history_rows, symbol=symbol)
        snapshot_scorer = FactorScorer(
            source_manager=snapshot_manager,
            registry=self.factor_scorer.registry,
            weight_manager=self.factor_scorer.weight_manager,
        )
        scores: list[dict[str, Any]] = []
        for idx in range(warmup_days, len(history_rows) - 1):
            snapshot_manager.set_index(idx)
            card = snapshot_scorer.score_symbol(
                symbol=symbol,
                market_state=market_state,
                proxy_symbol=proxy_symbol,
            ).to_dict()
            card["date"] = history_rows[idx]["date"]
            card["index"] = idx
            scores.append(card)
        return scores

    def _simulate(
        self,
        symbol: str,
        strategy: IStrategy,
        market_state: str,
        score_series: list[dict[str, Any]],
        history_rows: list[dict[str, Any]],
        snapshot_hash: str,
        config: BacktestConfig,
        effective_warmup_days: int,
    ) -> BacktestResult:
        index_map = {row["date"]: idx for idx, row in enumerate(history_rows)}
        equity = float(config.initial_capital)
        position = 0.0
        turnover = 0.0
        trades: list[dict[str, Any]] = []
        history_scorecards: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []
        if score_series:
            first_idx = score_series[0]["index"]
            equity_curve.append({"date": history_rows[first_idx]["date"], "equity": round(equity, 4)})
        for scorecard in score_series:
            date = str(scorecard["date"])
            idx = index_map[date]
            next_idx = idx + 1
            if next_idx >= len(history_rows):
                break
            signal = strategy.generate(scorecard, position, history_scorecards)
            target_position = max(0.0, min(1.0, float(signal.target_position)))
            if abs(target_position - position) > 1e-9:
                delta = abs(target_position - position)
                turnover += delta
                trading_cost = equity * delta * (config.fee_rate + config.slippage_bps / 10000.0)
                equity -= trading_cost
                trades.append(
                    {
                        "date": date,
                        "action": signal.action,
                        "from_position": round(position, 4),
                        "to_position": round(target_position, 4),
                        "cost": round(trading_cost, 4),
                        "reason": signal.reason,
                        "score": round(signal.score, 4),
                        "confidence": round(signal.confidence, 4),
                    }
                )
            daily_ret = _calc_return(history_rows[idx]["unit_nav"], history_rows[next_idx]["unit_nav"])
            equity *= 1.0 + target_position * daily_ret
            equity_curve.append({"date": history_rows[next_idx]["date"], "equity": round(equity, 4)})
            position = target_position
            history_scorecards.append(scorecard)
        metrics = compute_kpis(
            equity_curve=equity_curve,
            initial_capital=config.initial_capital,
            trade_count=len(trades),
            turnover=turnover,
        )
        return BacktestResult(
            strategy=strategy.name,
            symbol=symbol,
            market_state=market_state,
            snapshot_hash=snapshot_hash,
            config={**asdict(config), "effective_warmup_days": effective_warmup_days},
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            score_series=score_series,
        )

    @staticmethod
    def _hash_snapshot(history_rows: list[dict[str, Any]]) -> str:
        text = json.dumps(history_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class _SnapshotSourceManager:
    """Provide deterministic data slices for backtest factor scoring."""

    def __init__(self, history_rows: list[dict[str, Any]], symbol: str) -> None:
        self.history_rows = list(history_rows)
        self.symbol = symbol
        self._index = len(self.history_rows) - 1

    def set_index(self, index: int) -> None:
        self._index = max(0, min(index, len(self.history_rows) - 1))

    def fetch_history(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        limit = int(kwargs.get("limit", 60))
        prefix = self.history_rows[: self._index + 1]
        sliced = prefix[-limit:] if limit > 0 else prefix
        records = list(reversed(sliced))
        return {
            "metric": "history",
            "symbol": symbol,
            "source": "snapshot",
            "source_time": sliced[-1]["date"] if sliced else None,
            "records": records,
            "quality_score": 1.0,
            "stale": False,
            "metadata": {"snapshot_index": self._index},
        }

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> dict[str, Any]:
        prefix = self.history_rows[: self._index + 1]
        returns: list[float] = []
        for idx in range(1, len(prefix)):
            returns.append(_calc_return(prefix[idx - 1]["unit_nav"], prefix[idx]["unit_nav"]))
        last = returns[-3:] if len(returns) >= 3 else returns
        mean_ret = (sum(last) / len(last)) if last else 0.0
        inflow_ratio = mean_ret * 100.0 * 15.0
        return {
            "metric": "flow",
            "symbol": symbol or self.symbol,
            "source": "snapshot",
            "source_time": prefix[-1]["date"] if prefix else None,
            "records": [{"main_inflow_ratio": round(inflow_ratio, 4), "change_pct": round(mean_ret * 100.0, 4)}],
            "quality_score": 0.7,
            "stale": False,
            "metadata": {"synthetic": True},
        }

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> dict[str, Any]:
        prefix = self.history_rows[: self._index + 1]
        if len(prefix) >= 2:
            recent_ret = _calc_return(prefix[-2]["unit_nav"], prefix[-1]["unit_nav"])
        else:
            recent_ret = 0.0
        if recent_ret >= 0:
            records = [
                {"title": "政策利好", "content": "行业回暖，资金净流入"},
                {"title": "景气提升", "content": "市场预期上调，风险偏好改善"},
            ]
        else:
            records = [
                {"title": "风险提示", "content": "波动扩大，资金净流出"},
                {"title": "回撤预警", "content": "短期不确定性上升"},
            ]
        return {
            "metric": "news",
            "symbol": symbol or self.symbol,
            "source": "snapshot",
            "source_time": prefix[-1]["date"] if prefix else None,
            "records": records,
            "quality_score": 0.6,
            "stale": False,
            "metadata": {"synthetic": True},
        }


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _calc_return(start: float, end: float) -> float:
    if start <= 0:
        return 0.0
    return (end - start) / start
